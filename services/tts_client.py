"""Seslendirme servisi (Azure Speech uyumlu): SSML gonderir, ses dosyasi alir."""
import hashlib
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

import httpx

import config
from services.ssml_tools import ampersand_duzelt


class TTSHatasi(Exception):
    pass


def ssml_olustur(icerik: str) -> str:
    """LLM'den gelen <prosody>/<break> icerigini <speak><voice> zarfina koyar."""
    icerik = icerik.strip()

    # Icerik zaten tam bir <speak> belgesiyse oldugu gibi kullan
    if icerik.startswith("<speak"):
        return icerik

    icerik = ampersand_duzelt(icerik)

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


TEKRAR_KODLARI = {429, 500, 502, 503, 504}


def _onbellek_yolu(ssml: str):
    """Ayni SSML + ses + format icin daha once alinan sesi tekrar istememek icin."""
    anahtar = hashlib.sha256(
        f"{config.TTS_URL}|{config.TTS_OUTPUT_FORMAT}|{ssml}".encode("utf-8")
    ).hexdigest()
    return config.CIKTI_KLASORU / ".tts_cache" / f"{anahtar}.ses"


def _bekleme_suresi(yanit, deneme: int) -> float:
    if yanit is not None:
        try:
            return min(float(yanit.headers.get("Retry-After", "")), 60.0)
        except ValueError:
            pass
    return min(2 ** deneme, 30)   # 2, 4, 8, 16, 30 sn


def seslendir(icerik: str) -> tuple[bytes, str]:
    """Doner: (ses_baytlari, gonderilen_ssml)"""
    if not config.TTS_URL:
        raise TTSHatasi(".env dosyasinda TTS_URL tanimli degil.")
    if not config.TTS_VOICE:
        raise TTSHatasi(".env dosyasinda TTS_VOICE (ses modeli adi) tanimli degil.")

    ssml = ssml_olustur(icerik)
    ssml_kontrol(ssml)

    onbellek = _onbellek_yolu(ssml)
    if onbellek.exists() and onbellek.stat().st_size > 0:
        return onbellek.read_bytes(), ssml

    headerlar = {
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": config.TTS_OUTPUT_FORMAT,
    }
    if config.TTS_KEY:
        headerlar["Ocp-Apim-Subscription-Key"] = config.TTS_KEY

    son_hata = ""
    for deneme in range(1, config.TTS_RETRY + 2):   # ilk istek + TTS_RETRY tekrar
        yanit = None
        try:
            yanit = httpx.post(
                config.TTS_URL,
                content=ssml.encode("utf-8"),
                headers=headerlar,
                timeout=config.TTS_TIMEOUT,
                verify=config.VERIFY_SSL,
            )
        except httpx.ConnectError as e:
            son_hata = f"Seslendirme servisine baglanilamadi (ag/SSL): {e}"
        except httpx.TimeoutException:
            son_hata = f"Servis {config.TTS_TIMEOUT} sn icinde yanit vermedi."
        else:
            if yanit.status_code == 200 and yanit.content:
                onbellek.parent.mkdir(parents=True, exist_ok=True)
                onbellek.write_bytes(yanit.content)
                if config.TTS_BEKLEME > 0:
                    time.sleep(config.TTS_BEKLEME)
                return yanit.content, ssml
            if yanit.status_code == 200:
                raise TTSHatasi("Servis bos yanit dondu (SSML'i veya ses modeli adini kontrol edin).")
            son_hata = f"HTTP {yanit.status_code}: {yanit.text[:500]}"
            if yanit.status_code not in TEKRAR_KODLARI:
                raise TTSHatasi(son_hata)   # 400/401 gibi hatalarda tekrar denemenin anlami yok

        if deneme <= config.TTS_RETRY:
            time.sleep(_bekleme_suresi(yanit, deneme))

    raise TTSHatasi(f"{son_hata} ({config.TTS_RETRY + 1} deneme yapildi)")
