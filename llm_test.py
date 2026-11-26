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
metin = (Path(argumanlar[0]).read_text(encoding="utf-8") if argumanlar
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
except llm_client.LLMHatasi as e:
    print(f"\nHATA ({time.monotonic() - bas:.0f} sn): {e}")
    sys.exit(1)
print(f"\nBAŞARILI ({time.monotonic() - bas:.0f} sn). Yanıtın başı:\n{sonuc[:500]}")
