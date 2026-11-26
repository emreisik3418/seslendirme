"""Seslendirme (TTS) servisini uygulamadan bagimsiz dener: tek istek gonderir, sureyi ve sonucu yazar.

Kullanim (proje klasorunde):
    .venv\\Scripts\\python tts_test.py                -> kisa ornek cumle
    .venv\\Scripts\\python tts_test.py ssml.txt       -> dosyadaki icerik (LLM'den donen <prosody>... metni)
    .venv\\Scripts\\python tts_test.py --proxysiz     -> sistem proxy'sini kullanmadan dene
Basariliysa sesi tts_test.mp3 (veya .wav) olarak kaydeder. Onbellek kullanilmaz.
"""
import logging
import sys
import tempfile
import time
from pathlib import Path

import config
from services import tts_client
from services.llm_client import _proxy_bilgisi

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)

argumanlar = [a for a in sys.argv[1:] if not a.startswith("--")]
if "--proxysiz" in sys.argv:
    config.TTS_SISTEM_PROXY = False
config.TTS_RETRY = 0                       # tek deneme: sonucu hemen gorelim
_gecici = tempfile.mkdtemp(prefix="docvoice_tts_test_")
tts_client._onbellek_yolu = lambda ssml: Path(_gecici) / "x.ses"   # onbellege bakma (her calistirmada bos klasor)


def _oku(ad: str) -> str:
    yol = Path(ad)
    if not yol.exists() and Path(ad + ".txt").exists():
        yol = Path(ad + ".txt")
    if not yol.exists():
        print(f"HATA: dosya bulunamadı: {yol.resolve()}")
        sys.exit(1)
    for kod in ("utf-8-sig", "cp1254"):
        try:
            return yol.read_text(encoding=kod)
        except UnicodeDecodeError:
            continue
    return yol.read_text(encoding="utf-8", errors="replace")


icerik = _oku(argumanlar[0]) if argumanlar else \
    '<prosody rate="0%">Merhaba, bu bir seslendirme denemesidir.</prosody>'
vekil = _proxy_bilgisi(config.TTS_URL)
print(f"Python      : {sys.executable}")
print(f"TTS_URL     : {config.TTS_URL}")
print(f"Ses / format: {config.TTS_VOICE} · {config.TTS_OUTPUT_FORMAT}")
print(f"TTS_TIMEOUT : {config.TTS_TIMEOUT:.0f} sn")
print(f"Proxy       : {vekil if vekil and config.TTS_SISTEM_PROXY else 'yok, doğrudan bağlanılıyor'}")
print(f"İçerik      : {len(icerik)} karakter\n")

bas = time.monotonic()
try:
    ses, ssml = tts_client.seslendir(icerik)
except Exception as e:
    print(f"\nHATA ({time.monotonic() - bas:.0f} sn, {type(e).__name__}): {e}")
    sys.exit(1)
dosya = Path(f"tts_test.{tts_client.dosya_uzantisi()}")
dosya.write_bytes(ses)
print(f"\nBAŞARILI ({time.monotonic() - bas:.0f} sn): {len(ses)} bayt ses -> {dosya.resolve()}")
