"""LLM servisini uygulamadan bagimsiz dener: tek istek gonderir, sureyi ve sonucu yazar.

Kullanim (proje klasorunde):
    .venv\\Scripts\\python llm_test.py                  -> kural seti + kisa ornek metin
    .venv\\Scripts\\python llm_test.py metin.txt        -> kural seti + dosyadaki metin (Bruno'daki metni koyun)
    .venv\\Scripts\\python llm_test.py --proxysiz       -> sistem proxy'sini kullanmadan dene
"""
import logging
import sys
import time
from pathlib import Path

import config
from services import llm_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)

argumanlar = [a for a in sys.argv[1:] if not a.startswith("--")]
if "--proxysiz" in sys.argv:
    config.LLM_SISTEM_PROXY = False
config.LLM_PARALEL = 1

kurallar = config.KURALLAR_DOSYASI.read_text(encoding="utf-8") if config.KURALLAR_DOSYASI.exists() else ""


def _metin_oku(ad: str) -> str:
    """UTF-8 (BOM'lu/BOM'suz) ve Turkce Windows (ANSI / cp1254) kodlamalarini dener; .txt.txt hatasini yakalar."""
    yol = Path(ad)
    if not yol.exists() and Path(ad + ".txt").exists():
        yol = Path(ad + ".txt")      # Windows uzantiyi gizleyince dosya adi metin.txt.txt olabiliyor
    if not yol.exists():
        print(f"HATA: dosya bulunamadı: {yol.resolve()}")
        sys.exit(1)
    for kod in ("utf-8-sig", "cp1254"):
        try:
            return yol.read_text(encoding=kod)
        except UnicodeDecodeError:
            continue
    return yol.read_text(encoding="utf-8", errors="replace")


metin = (_metin_oku(argumanlar[0]) if argumanlar
         else "Mevduat bakiyesi geçen aya göre yüzde üç arttı. Faiz gelirleri hedefin üzerinde gerçekleşti.")

print(f"Python        : {sys.executable}")
print(f"LLM_URL       : {config.LLM_URL}")
print(f"LLM_TIMEOUT   : {config.LLM_TIMEOUT:.0f} sn")
vekil = llm_client._proxy_bilgisi()
print(f"Proxy         : {vekil if vekil and config.LLM_SISTEM_PROXY else 'yok, doğrudan bağlanılıyor'}"
      + (" (LLM_SISTEM_PROXY=false ile atlandı)" if vekil and not config.LLM_SISTEM_PROXY else ""))
print(f"Kural seti    : {len(kurallar)} karakter · Metin: {len(metin)} karakter\n")

bas = time.monotonic()
try:
    sonuc, _ = llm_client.formatla(kurallar, metin)
except Exception as e:   # LLMHatasi veya beklenmeyen hata: turunu ve suresini goster
    print(f"\nHATA ({time.monotonic() - bas:.0f} sn, {type(e).__name__}): {e}")
    sys.exit(1)
print(f"\nBAŞARILI ({time.monotonic() - bas:.0f} sn). Yanıtın başı:\n{sonuc[:500]}")
