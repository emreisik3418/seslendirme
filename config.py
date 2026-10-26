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

# --- Video ---
VIDEO_BG = os.getenv("VIDEO_BG", "#0E1A2B")          # arka plan ust renk
VIDEO_BG2 = os.getenv("VIDEO_BG2", "#16304F")        # arka plan alt renk
VIDEO_ACCENT = os.getenv("VIDEO_ACCENT", "#2EC4B6")  # vurgu rengi
VIDEO_LOGO = os.getenv("VIDEO_LOGO", "")             # logo dosya yolu (PNG, istege bagli)
VIDEO_FONT = os.getenv("VIDEO_FONT", "")             # bos: Segoe UI / Arial
VIDEO_FONT_BOLD = os.getenv("VIDEO_FONT_BOLD", "")
VIDEO_FFMPEG = os.getenv("VIDEO_FFMPEG", "")         # bos: imageio-ffmpeg'den otomatik

# --- Genel ---
# SSL dogrulamasi: once true ile deneyin. Sadece zorunlu kalirsaniz false yapin.
VERIFY_SSL = _bool("VERIFY_SSL", True)

KURALLAR_DOSYASI = PROJE_KLASORU / "rules" / "kurallar.txt"
CIKTI_KLASORU = PROJE_KLASORU / "output"
