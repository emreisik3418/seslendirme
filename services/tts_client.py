"""Seslendirme servisi (Azure Speech uyumlu): SSML gonderir, ses dosyasi alir."""
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

import httpx

import config


class TTSHatasi(Exception):
    pass


def ssml_olustur(icerik: str) -> str:
    """LLM'den gelen <prosody>/<break> icerigini <speak><voice> zarfina koyar."""
    icerik = icerik.strip()

    # Icerik zaten tam bir <speak> belgesiyse oldugu gibi kullan
    if icerik.startswith("<speak"):
        return icerik

    # Metin icindeki tek basina '&' isaretleri XML'i bozar (orn. "Ar&Ge")
    icerik = re.sub(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", icerik)

    lexicon = f"<lexicon uri={quoteattr(config.TTS_LEXICON)}/>" if config.TTS_LEXICON else ""
    return (
        '<speak xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="http://www.w3.org/2001/mstts" '
        'xmlns:emo="http://www.w3.org/2009/10/emotionml" '
        f'version="1.0" xml:lang={quoteattr(config.TTS_LANG)}>'
        f"<voice name={quoteattr(config.TTS_VOICE)}>"
        f"{lexicon}{icerik}"
        "</voice></speak>"
    )


def ssml_kontrol(ssml: str) -> None:
    """Gondermeden once XML gecerli mi bak; hatayi anlasilir sekilde soyle."""
    try:
        ET.fromstring(ssml)
    except ET.ParseError as e:
        raise TTSHatasi(
            f"SSML gecersiz: {e}. Genelde kapanmamis bir <prosody> etiketi "
            "veya metindeki ozel bir karakter sebep olur."
        ) from e


def dosya_uzantisi() -> str:
    f = config.TTS_OUTPUT_FORMAT.lower()
    if "mp3" in f:
        return "mp3"
    if "riff" in f or "wav" in f:
        return "wav"
    if "ogg" in f or "opus" in f:
        return "ogg"
    if "webm" in f:
        return "webm"
    return "bin"


def seslendir(icerik: str) -> tuple[bytes, str]:
    """Doner: (ses_baytlari, gonderilen_ssml)"""
    if not config.TTS_URL:
        raise TTSHatasi(".env dosyasinda TTS_URL tanimli degil.")
    if not config.TTS_VOICE:
        raise TTSHatasi(".env dosyasinda TTS_VOICE (ses modeli adi) tanimli degil.")

    ssml = ssml_olustur(icerik)
    ssml_kontrol(ssml)

    headerlar = {
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": config.TTS_OUTPUT_FORMAT,
    }
    if config.TTS_KEY:
        headerlar["Ocp-Apim-Subscription-Key"] = config.TTS_KEY

    try:
        yanit = httpx.post(
            config.TTS_URL,
            content=ssml.encode("utf-8"),
            headers=headerlar,
            timeout=config.TTS_TIMEOUT,
            verify=config.VERIFY_SSL,
        )
    except httpx.ConnectError as e:
        raise TTSHatasi(f"Seslendirme servisine baglanilamadi (ag/SSL): {e}") from e
    except httpx.TimeoutException as e:
        raise TTSHatasi(f"Servis {config.TTS_TIMEOUT} sn icinde yanit vermedi.") from e

    if yanit.status_code != 200:
        raise TTSHatasi(f"HTTP {yanit.status_code}: {yanit.text[:1000]}")
    if not yanit.content:
        raise TTSHatasi("Servis bos yanit dondu (SSML'i veya ses modeli adini kontrol edin).")

    return yanit.content, ssml
