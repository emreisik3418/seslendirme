"""Seslendirme servisi (Azure Speech uyumlu): SSML gonderir, ses dosyasi alir."""
import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

import httpx

import config
from services.ssml_tools import ssml_onar


log = logging.getLogger("docvoice.tts")


class TTSHatasi(Exception):
    pass


def ssml_olustur(icerik: str) -> str:
    """LLM'den gelen <prosody>/<break> icerigini <speak><voice> zarfina koyar."""
    # Hatali etiketleri onar; <speak>/<voice> zarfi varsa kaldirilip .env ayarlariyla yeniden kurulur
    icerik, _ = ssml_onar(icerik.strip())

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


def yanit_ozeti(yanit: httpx.Response) -> str:
    """Hata yaniti HTML ise (proxy / gateway hata sayfasi) basligini ve gorunen metnini cikarir,
    sayfanin tamamini output/tts_son_hata.html dosyasina yazar. Degilse ilk 300 karakter."""
    import re

    metin = yanit.text or ""
    if "<html" not in metin[:2000].lower() and "<!doctype" not in metin[:200].lower():
        return metin[:300]
    try:
        dosya = config.CIKTI_KLASORU / "tts_son_hata.html"
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text(metin, encoding="utf-8")
        kayit = f" [sayfanın tamamı: {dosya}]"
    except OSError:
        kayit = ""
    baslik = re.search(r"<title[^>]*>(.*?)</title>", metin, re.S | re.I)
    govde = re.sub(r"<(style|script|head)[^>]*>.*?</\1>", " ", metin, flags=re.S | re.I)
    govde = re.sub(r"<[^>]+>", " ", govde)
    govde = re.sub(r"\s+", " ", govde).strip()
    sunucu = yanit.headers.get("server") or yanit.headers.get("via") or ""
    parcalar = ["HTML sayfası (servisten değil, aradaki bir cihazdan geliyor olabilir)"]
    if sunucu:
        parcalar.append(f"gönderen: {sunucu}")
    if baslik:
        baslik_metni = re.sub(r"\s+", " ", baslik.group(1)).strip()[:120]
        parcalar.append(f"başlık: {baslik_metni}")
    if govde:
        parcalar.append(f"metin: {govde[:300]}")
    return " · ".join(parcalar) + kayit


def windows_proxy(url: str) -> str:
    """Windows Internet Ayarlari'ndaki elle girilmis proxy (Bruno, tarayici bunu kullanir). PAC desteklenmez."""
    import urllib.request
    from urllib.parse import urlsplit

    if not hasattr(urllib.request, "getproxies_registry"):
        return ""
    host = urlsplit(url).hostname or ""
    try:
        if host and urllib.request.proxy_bypass_registry(host):
            return ""
        vekiller = urllib.request.getproxies_registry()
    except OSError:
        return ""
    return vekiller.get(urlsplit(url).scheme) or vekiller.get("https") or vekiller.get("http") or ""


def proxy_secimi() -> tuple[str, bool]:
    """Doner: (kullanilacak proxy adresi veya "", ortam degiskenlerine bakilsin mi)."""
    from services.llm_client import _proxy_bilgisi

    ayar = config.TTS_PROXY.lower()
    if ayar in ("yok", "none", "false", "hayir"):
        return "", False
    if ayar in ("windows", "sistem", "system"):
        return windows_proxy(config.TTS_URL), False
    if ayar:
        return config.TTS_PROXY, False
    return (_proxy_bilgisi(config.TTS_URL), True) if config.TTS_SISTEM_PROXY else ("", False)


def _istemci(zaman, proxy: str, ortam: bool) -> httpx.Client:
    ayar = dict(timeout=zaman, verify=config.ssl_dogrulama(), trust_env=ortam)
    if proxy and not ortam:
        try:
            return httpx.Client(proxy=proxy, **ayar)
        except TypeError:                      # eski httpx surumleri
            return httpx.Client(proxies=proxy, **ayar)
    return httpx.Client(**ayar)


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
    if config.TTS_USER_AGENT:
        headerlar["User-Agent"] = config.TTS_USER_AGENT

    proxy, ortam = proxy_secimi()
    if proxy:
        ipucu = (f" İstek {proxy} proxy'si üzerinden gidiyor; Bruno'da çalışıp burada çalışmıyorsa "
                 ".env'de TTS_PROXY=yok veya TTS_PROXY=windows deneyin.")
    elif config.TTS_PROXY.lower() in ("windows", "sistem", "system"):
        ipucu = (" TTS_PROXY=windows ama Windows'ta elle tanımlı proxy bulunamadı (otomatik yapılandırma / PAC "
                 "kullanılıyor olabilir): ağ ekibinden proxy adresini alıp TTS_PROXY=http://adres:port yazın.")
    else:
        ipucu = (" İstek proxy'siz, doğrudan gidiyor. Bruno'da çalışıyorsa Bruno büyük ihtimalle Windows'un "
                 "proxy ayarını kullanıyor: .env'de TTS_PROXY=windows deneyin (ayrıntı için tts_test.py).")
    zaman = httpx.Timeout(config.TTS_TIMEOUT)     # onceki surumle ayni: baglanti dahil her asamada TTS_TIMEOUT

    son_hata = ""
    for deneme in range(1, config.TTS_RETRY + 2):   # ilk istek + TTS_RETRY tekrar
        yanit = None
        bas = time.monotonic()
        log.info(f"TTS isteği: {len(ssml)} karakter SSML" + (f" (proxy: {proxy})" if proxy else "")
                 + (f", {deneme}. deneme" if deneme > 1 else ""))
        try:
            with _istemci(zaman, proxy, ortam) as istemci:
                yanit = istemci.post(config.TTS_URL, content=ssml.encode("utf-8"), headers=headerlar)
        except httpx.ConnectTimeout:
            sn = time.monotonic() - bas
            son_hata = (f"Seslendirme servisine {sn:.0f} sn içinde bağlanılamadı (ağ / proxy / güvenlik duvarı"
                        + ("; ~21 sn Windows'un kendi bağlantı denemesi süresidir, sunucu adrese hiç ulaşamıyor"
                           if 15 < sn < 25 else "") + f").{ipucu}")
        except httpx.ConnectError as e:
            son_hata = f"Seslendirme servisine bağlanılamadı (ağ/SSL): {e}{ipucu}"
        except httpx.TimeoutException:
            son_hata = f"Servis {config.TTS_TIMEOUT:.0f} sn içinde yanıt vermedi.{ipucu}"
        except httpx.TransportError as e:   # yanit gelmeden baglanti koptu (proxy / gateway)
            son_hata = (f"Bağlantı {time.monotonic() - bas:.0f} sn sonra yanıt gelmeden kapandı "
                        f"({type(e).__name__}: {e}). Aradaki proxy / gateway'in zaman aşımı olabilir.{ipucu}")
        else:
            sure = time.monotonic() - bas
            log.info(f"TTS yanıtı: HTTP {yanit.status_code}, {len(yanit.content)} bayt, {sure:.0f} sn")
            if yanit.status_code == 200 and yanit.content:
                onbellek.parent.mkdir(parents=True, exist_ok=True)
                onbellek.write_bytes(yanit.content)
                if config.TTS_BEKLEME > 0:
                    time.sleep(config.TTS_BEKLEME)
                return yanit.content, ssml
            if yanit.status_code == 200:
                raise TTSHatasi("Servis boş yanıt döndü (SSML'i veya ses modeli adını kontrol edin).")
            aciklama = {
                400: " İstek reddedildi: SSML'de servisin tanımadığı bir etiket / değer veya yanlış ses adı "
                     "(TTS_VOICE) olabilir.",
                401: " Anahtar (TTS_KEY) geçersiz veya eksik.",
                403: " Bu anahtarın / uygulamanın servise erişim izni yok.",
                413: " SSML çok uzun; LLM kural setinde daha kısa bölümler (<break>) isteyin.",
                429: " Servis istek sınırına takıldı; TTS_BEKLEME değerini artırın (ör. 2).",
                502: f" Aradaki gateway hata verdi ({sure:.0f} sn).",
                503: " Servis meşgul / bakımda.",
                504: f" Aradaki gateway {sure:.0f} sn sonra zaman aşımına uğradı.",
            }.get(yanit.status_code, "")
            yol = f" İstek {proxy} proxy'si üzerinden gitti." if proxy else " İstek doğrudan (proxy'siz) gitti."
            son_hata = f"HTTP {yanit.status_code}.{aciklama}{yol} Yanıt: {yanit_ozeti(yanit)}"
            if yanit.status_code not in TEKRAR_KODLARI:
                raise TTSHatasi(son_hata)   # 400/401 gibi hatalarda tekrar denemenin anlami yok
        log.warning(f"TTS hatası ({deneme}. deneme): {son_hata}")

        if deneme <= config.TTS_RETRY:
            time.sleep(_bekleme_suresi(yanit, deneme))

    raise TTSHatasi(f"{son_hata} ({config.TTS_RETRY + 1} deneme yapıldı)")
