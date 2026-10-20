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
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))

# --- TTS servisi (bilgiler gelince doldurulacak) ---
TTS_URL = os.getenv("TTS_URL", "")
TTS_APP_NAME = os.getenv("TTS_APP_NAME", "")
TTS_TOKEN = os.getenv("TTS_TOKEN", "")

# --- Genel ---
# SSL dogrulamasi: once true ile deneyin. Sadece zorunlu kalirsaniz false yapin.
VERIFY_SSL = _bool("VERIFY_SSL", True)

KURALLAR_DOSYASI = PROJE_KLASORU / "rules" / "kurallar.txt"
CIKTI_KLASORU = PROJE_KLASORU / "output"
