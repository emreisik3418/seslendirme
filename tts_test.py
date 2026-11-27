"""Seslendirme (TTS) servisini uygulamadan bagimsiz dener: tek istek gonderir, sureyi ve sonucu yazar.

Kullanim (proje klasorunde):
    .venv\\Scripts\\python tts_test.py                -> kisa ornek cumle
    .venv\\Scripts\\python tts_test.py ssml.txt       -> dosyadaki icerik (LLM'den donen <prosody>... metni)
    .venv\\Scripts\\python tts_test.py --proxysiz     -> ortam proxy'sini kullanmadan dene
    .venv\\Scripts\\python tts_test.py --windows      -> Windows Internet Ayarlari'ndaki proxy ile dene
    .venv\\Scripts\\python tts_test.py --tek          -> ilk deneme basarisiz olsa da baska yol deneme
Ilk deneme basarisiz olursa proxy'siz, Windows proxy'si ve farkli User-Agent ile kendiliginden dener.
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
    config.TTS_PROXY = "yok"
if "--windows" in sys.argv:
    config.TTS_PROXY = "windows"
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


def ag_tanilama():
    """DNS, dogrudan TCP baglantisi ve proxy ayarlarini yazar: Bruno ile farki gormek icin."""
    import socket
    from urllib.parse import urlsplit

    p = urlsplit(config.TTS_URL)
    host, port = p.hostname or "", p.port or (443 if p.scheme == "https" else 80)
    print(f"--- Ağ kontrolü: {host}:{port}")
    try:
        adresler = sorted({a[4][0] for a in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
        print(f"DNS         : {', '.join(adresler)}")
    except OSError as e:
        print(f"DNS         : ÇÖZÜLEMEDİ ({e})")
        adresler = []
    dogrudan = False
    for ip in adresler:
        bas = time.monotonic()
        try:
            with socket.create_connection((ip, port), timeout=8):
                dogrudan = True
                print(f"Doğrudan TCP: {ip} -> BAĞLANDI ({(time.monotonic() - bas) * 1000:.0f} ms)")
        except OSError as e:
            print(f"Doğrudan TCP: {ip} -> BAĞLANAMADI ({time.monotonic() - bas:.0f} sn, {e})")
    ortam = _proxy_bilgisi(config.TTS_URL)
    win = tts_client.windows_proxy(config.TTS_URL)
    pac = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as k:
            pac = winreg.QueryValueEx(k, "AutoConfigURL")[0]
    except (ImportError, OSError):
        pass
    print(f"Ortam proxy : {ortam or 'yok'}   (HTTPS_PROXY vb.; Python bunu kullanır)")
    print(f"Windows prx : {win or 'yok'}   (Internet Ayarları; Bruno / tarayıcı bunu kullanabilir)")
    if pac:
        print(f"Windows PAC : {pac}   (otomatik yapılandırma betiği; Python desteklemez)")
    secilen, _ = tts_client.proxy_secimi()
    print(f"Kullanılacak: {secilen or 'proxy yok, doğrudan'}   (TTS_PROXY={config.TTS_PROXY or 'boş'})")
    if not dogrudan and win and not secilen:
        print("ÖNERİ      : doğrudan bağlantı yok ama Windows'ta proxy tanımlı -> .env'ye TTS_PROXY=windows ekleyin")
    elif not dogrudan and pac and not secilen:
        print("ÖNERİ      : doğrudan bağlantı yok, Windows PAC kullanıyor -> ağ ekibinden proxy adresini alıp "
              "TTS_PROXY=http://adres:port yazın")
    print()


print(f"Python      : {sys.executable}")
print(f"TTS_URL     : {config.TTS_URL}")
print(f"Ses / format: {config.TTS_VOICE} · {config.TTS_OUTPUT_FORMAT}")
print(f"TTS_TIMEOUT : {config.TTS_TIMEOUT:.0f} sn")
print(f"İçerik      : {len(icerik)} karakter\n")
ag_tanilama()

TARAYICI_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DocVoice/1.0"


def dene(ad: str, proxy: str | None = None, ua: str | None = None):
    """Tek istek; ayarlari gecici olarak degistirir. Doner: ses baytlari veya None."""
    eski = (config.TTS_PROXY, config.TTS_USER_AGENT)
    if proxy is not None:
        config.TTS_PROXY = proxy
    if ua is not None:
        config.TTS_USER_AGENT = ua
    secilen, _ = tts_client.proxy_secimi()
    print(f"--- Deneme: {ad}  (proxy: {secilen or 'yok'}, User-Agent: {config.TTS_USER_AGENT or 'python-httpx'})")
    bas = time.monotonic()
    try:
        ses, _ = tts_client.seslendir(icerik)
    except Exception as e:
        print(f"    HATA ({time.monotonic() - bas:.0f} sn, {type(e).__name__}): {e}\n")
        return None
    finally:
        config.TTS_PROXY, config.TTS_USER_AGENT = eski
    print(f"    BAŞARILI ({time.monotonic() - bas:.0f} sn): {len(ses)} bayt ses\n")
    return ses


ses = dene("şu anki .env ayarları")
oneri = ""
if ses is None and "--tek" not in sys.argv:
    print("İlk deneme başarısız; farklı yollar deneniyor (her biri tek istek).\n")
    secenekler = [("proxy'siz, doğrudan", "yok", None, "TTS_PROXY=yok")]
    if tts_client.windows_proxy(config.TTS_URL):
        secenekler.append(("Windows proxy'si (Bruno gibi)", "windows", None, "TTS_PROXY=windows"))
    secenekler += [
        ("farklı User-Agent", None, TARAYICI_UA, f"TTS_USER_AGENT={TARAYICI_UA}"),
        ("proxy'siz + farklı User-Agent", "yok", TARAYICI_UA, f"TTS_PROXY=yok ve TTS_USER_AGENT={TARAYICI_UA}"),
    ]
    for ad, proxy, ua, ayar in secenekler:
        ses = dene(ad, proxy, ua)
        if ses is not None:
            oneri = ayar
            break

if ses is None:
    print("SONUÇ: hiçbir yol çalışmadı. Yukarıdaki HATA satırlarını (özellikle HTML sayfasının başlığını) "
          "paylaşın; sayfanın tamamı output/tts_son_hata.html dosyasında.")
    sys.exit(1)
dosya = Path(f"tts_test.{tts_client.dosya_uzantisi()}")
dosya.write_bytes(ses)
print(f"SONUÇ: BAŞARILI, ses -> {dosya.resolve()}")
if oneri:
    print(f"ÇÖZÜM: .env dosyasına şunu ekleyin ve uygulamayı yeniden başlatın:\n    {oneri.replace(' ve ', chr(10) + '    ')}")
