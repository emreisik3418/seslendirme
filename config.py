"""Ayarlar .env dosyasindan okunur. Kod icine adres veya sifre yazilmaz."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJE_KLASORU = Path(__file__).parent
load_dotenv(PROJE_KLASORU / ".env")

# Sirket sertifikalari icin: Python, Windows'un sertifika deposunu kullansin.
# (truststore kurulu degilse sessizce atlanir.)
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass


def _bool(ad: str, varsayilan: bool) -> bool:
    deger = os.getenv(ad)
    if deger is None:
        return varsayilan
    return deger.strip().lower() in ("1", "true", "evet", "yes")


# --- LLM servisi ---
LLM_URL = os.getenv("LLM_URL", "")
LLM_APP_NAME = os.getenv("LLM_APP_NAME", "")      # x-application-name header'i
LLM_TOKEN = os.getenv("LLM_TOKEN", "")            # Auth gerekiyorsa (Bearer)
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "400"))  # saniye; servis uzun surebiliyor
LLM_PARALEL = int(os.getenv("LLM_PARALEL", "3"))     # PDF modunda ayni anda gonderilen sayfa sayisi

# --- TTS servisi (Azure uyumlu, SSML alir) ---
TTS_URL = os.getenv("TTS_URL", "")
TTS_KEY = os.getenv("TTS_KEY", "")                # Ocp-Apim-Subscription-Key
TTS_OUTPUT_FORMAT = os.getenv("TTS_OUTPUT_FORMAT", "audio-24khz-48kbitrate-mono-mp3")
TTS_VOICE = os.getenv("TTS_VOICE", "")            # <voice name="...">
TTS_LEXICON = os.getenv("TTS_LEXICON", "")        # <lexicon uri="..."> (bos birakilabilir)
TTS_LANG = os.getenv("TTS_LANG", "tr-TR")
TTS_TIMEOUT = float(os.getenv("TTS_TIMEOUT", "300"))
TTS_RETRY = int(os.getenv("TTS_RETRY", "4"))          # 503/429 gibi gecici hatalarda tekrar sayisi
TTS_BEKLEME = float(os.getenv("TTS_BEKLEME", "0.3"))  # istekler arasi bekleme (sn)

# --- Video ---
UYARILAR: list[str] = []   # arayuzde yan panelde gosterilir


def _renk(ad: str, varsayilan: str) -> str:
    """Renk ayarini dogrular. Kabul edilir: #E30613, E30613, #FFF, red, rgb(227,6,19).
    Bos veya gecersizse varsayilan kullanilir ve uyari eklenir."""
    from PIL import ImageColor

    deger = (os.getenv(ad) or "").strip().strip("'\"")
    if not deger:
        return varsayilan
    adaylar = [deger]
    if not deger.startswith("#") and len(deger) in (3, 6):
        adaylar.append("#" + deger)       # diyezsiz hex: E30613
    for aday in adaylar:
        try:
            r, g, b = ImageColor.getrgb(aday)[:3]
            return f"#{r:02X}{g:02X}{b:02X}"
        except ValueError:
            continue
    UYARILAR.append(f"{ad}={deger} geçerli bir renk değil, varsayılan ({varsayilan}) kullanıldı.")
    return varsayilan


VIDEO_BG = _renk("VIDEO_BG", "#0E1A2B")          # arka plan ust renk
VIDEO_BG2 = _renk("VIDEO_BG2", "#16304F")        # arka plan alt renk
VIDEO_ACCENT = _renk("VIDEO_ACCENT", "#2EC4B6")  # vurgu rengi


def _logo_yolu() -> str:
    """Logo yolunu cozer: tirnak, ~, %USERPROFILE% ve proje klasorune gore goreli yol desteklenir."""
    ham = (os.getenv("VIDEO_LOGO") or "").strip().strip("'\"")
    if not ham:
        return ""
    yol = Path(os.path.expandvars(os.path.expanduser(ham)))
    if not yol.is_absolute():
        yol = PROJE_KLASORU / yol
    if not yol.exists():
        ipucu = ""
        if any(ord(c) < 32 for c in ham):
            ipucu = (" Yol çift tırnak içinde ters eğik çizgiyle yazılmış olabilir; "
                     "tırnaksız yazın veya / kullanın (C:/Users/.../logo.png).")
        UYARILAR.append(f"VIDEO_LOGO dosyası bulunamadı: {ham}.{ipucu}")
        return ""
    if yol.suffix.lower() == ".svg":
        UYARILAR.append("VIDEO_LOGO: SVG desteklenmiyor, logoyu PNG olarak kaydedin.")
        return ""
    try:
        from PIL import Image

        with Image.open(yol) as img:
            img.verify()
    except Exception as e:
        UYARILAR.append(f"VIDEO_LOGO açılamadı ({yol.name}): {e}")
        return ""
    return str(yol)


VIDEO_LOGO = _logo_yolu()                            # logo dosya yolu (PNG/JPG, istege bagli)
# Slayt modunda logonun arkasina beyaz kutu: "otomatik" (koyu logoda acik), true veya false
VIDEO_LOGO_ZEMIN = (os.getenv("VIDEO_LOGO_ZEMIN") or "otomatik").strip().lower()
VIDEO_FONT = os.getenv("VIDEO_FONT", "")             # bos: Segoe UI / Arial
VIDEO_FONT_BOLD = os.getenv("VIDEO_FONT_BOLD", "")
VIDEO_SUNUM = _bool("VIDEO_SUNUM", True)            # PDF modunda gosterge kartlarini yeniden ciz
VIDEO_ALTYAZI = _bool("VIDEO_ALTYAZI", True)        # arayuzdeki "Altyazi goster" varsayilani
VIDEO_FFMPEG = os.getenv("VIDEO_FFMPEG", "")         # bos: imageio-ffmpeg'den otomatik

# --- Genel ---
# SSL dogrulamasi: once true ile deneyin. Sadece zorunlu kalirsaniz false yapin.
VERIFY_SSL = _bool("VERIFY_SSL", True)

KURALLAR_DOSYASI = PROJE_KLASORU / "rules" / "kurallar.txt"
CIKTI_KLASORU = PROJE_KLASORU / "output"


def _yol(ad: str) -> Path | None:
    """Klasor yolu ayari: tirnak, ~, %USERPROFILE%, ag paylasimi (\\\\sunucu\\klasor) ve
    proje klasorune gore goreli yol desteklenir."""
    ham = (os.getenv(ad) or "").strip().strip("'\"")
    if not ham:
        return None
    if any(ord(c) < 32 for c in ham):
        UYARILAR.append(f"{ad}: yol çift tırnak içinde ters eğik çizgiyle yazılmış olabilir; "
                        "tırnaksız yazın veya / kullanın.")
    yol = Path(os.path.expandvars(os.path.expanduser(ham)))
    return yol if yol.is_absolute() else PROJE_KLASORU / yol


# --- Klasor izleyici (izleyici.py) ---
IZLE_KLASORU = _yol("IZLE_KLASORU")                  # yeni PDF'lerin dusecegi klasor
IZLE_HEDEF_KLASORU = _yol("IZLE_HEDEF_KLASORU")      # videolarin aktarilacagi klasor
IZLE_ARALIK = float(os.getenv("IZLE_ARALIK", "10"))  # klasor kac saniyede bir kontrol edilsin
IZLE_BEKLEME = float(os.getenv("IZLE_BEKLEME", "5")) # dosya boyutu bu kadar sn degismezse kopyalama bitti sayilir
IZLE_KURALLAR = _yol("IZLE_KURALLAR")                # bos: rules/kurallar.txt
IZLE_SRT = _bool("IZLE_SRT", True)                   # .srt altyazi dosyasini da hedefe kopyala
