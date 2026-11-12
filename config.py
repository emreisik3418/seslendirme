"""Ayarlar .env dosyasindan okunur. Kod icine adres veya sifre yazilmaz."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJE_KLASORU = Path(__file__).parent
load_dotenv(PROJE_KLASORU / ".env")

import ssl as _ssl

# Qlik gibi kendi kok sertifikasi olan sunucular icin standart SSL sinifi
ORIJINAL_SSLCONTEXT = _ssl.SSLContext


def ssl_dogrulama():
    """LLM / TTS servisleri icin SSL dogrulama ayari (httpx verify=).
    Sirket sertifikalari icin Windows'un sertifika deposu kullanilir (truststore paketi).
    truststore uygulama geneline enjekte edilmez; boylece Qlik'in root.pem ile dogrulamasi bozulmaz."""
    if not VERIFY_SSL:
        return False
    try:
        import truststore
        return truststore.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True


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
VIDEO_KARAKTER = _bool("VIDEO_KARAKTER", False)      # sag altta konusan 2D sunucu karakteri
try:
    VIDEO_KARAKTER_BOYUT = float(os.getenv("VIDEO_KARAKTER_BOYUT", "0.8"))  # 0.4 - 1.2
except ValueError:
    VIDEO_KARAKTER_BOYUT = 0.8
VIDEO_SAYFA_NO = _bool("VIDEO_SAYFA_NO", False)
VIDEO_PDF_TAM_EKRAN = _bool("VIDEO_PDF_TAM_EKRAN", True)   # PDF kenarlarini kirp, tum ekrani kullan
VIDEO_ALTYAZI_STIL = (os.getenv("VIDEO_ALTYAZI_STIL") or "kutusuz").strip().lower()   # kutusuz | kutu
VIDEO_ILERLEME = _bool("VIDEO_ILERLEME", True)            # en altta ince ilerleme cizgisi      # sag ustte sayfa numarasi
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

# Kendi karakter gorselleriniz (kapali.png, yarim.png, acik.png, kirpik.png); bos: yerlesik karakter
KARAKTER_KLASORU = _yol("KARAKTER_KLASORU")
# Fotograftan konusan karakter (yuvarlak cerceve). Fotograf repoya konmaz; yolunu buraya yazin.
KARAKTER_FOTO = _yol("KARAKTER_FOTO")
if KARAKTER_FOTO and not KARAKTER_FOTO.exists():
    UYARILAR.append(f"KARAKTER_FOTO dosyası bulunamadı: {KARAKTER_FOTO}")
    KARAKTER_FOTO = None
# Otomatik bulunamazsa: sol_goz_x,sol_goz_y;sag_goz_x,sag_goz_y;agiz_x,agiz_y (fotograf pikselleri)
KARAKTER_FOTO_NOKTALAR = (os.getenv("KARAKTER_FOTO_NOKTALAR") or "").strip().strip("'\"")
# Cerceve icindeki zemin: renk (#EEF2F7) veya "orijinal" (fotografin kendi arka plani)
KARAKTER_FOTO_ZEMIN = (os.getenv("KARAKTER_FOTO_ZEMIN") or "").strip().strip("'\"")
# Varsayilan karakter: sunucu (kadin), maya (maskot), foto (KARAKTER_FOTO) veya ozel (KARAKTER_KLASORU)
VIDEO_KARAKTER_TIPI = (os.getenv("VIDEO_KARAKTER_TIPI")
                       or ("foto" if KARAKTER_FOTO else "ozel" if KARAKTER_KLASORU else "sunucu")).strip().lower()

# --- Qlik Sense (QRS API ile content library'ye video yukleme) ---
QLIK_URL = (os.getenv("QLIK_URL") or "").strip().rstrip("/")       # https://qliksunucu:4242 veya https://qliksunucu/vproxy
QLIK_KUTUPHANE = (os.getenv("QLIK_KUTUPHANE") or "DocVoice").strip()
QLIK_KIMLIK = (os.getenv("QLIK_KIMLIK") or "sertifika").strip().lower()   # sertifika | header
QLIK_KULLANICI = (os.getenv("QLIK_KULLANICI") or "").strip()      # sertifika: UserDirectory=X; UserId=Y  header: DOMAIN\kullanici
QLIK_HEADER_ADI = (os.getenv("QLIK_HEADER_ADI") or "X-Qlik-User").strip()
QLIK_SERTIFIKA = _yol("QLIK_SERTIFIKA")           # client.pem
QLIK_ANAHTAR = _yol("QLIK_ANAHTAR")               # client_key.pem
QLIK_KOK_SERTIFIKA = _yol("QLIK_KOK_SERTIFIKA")   # root.pem (bos: Windows sertifika deposu)
QLIK_SSL_DOGRULA = _bool("QLIK_SSL_DOGRULA", True)
QLIK_HOST_KONTROL = _bool("QLIK_HOST_KONTROL", False)   # Qlik sertifikalari genelde makine adina verilir
QLIK_ICERIK_URL = (os.getenv("QLIK_ICERIK_URL") or "").strip().rstrip("/")   # izleme adresinin koku (bos: QLIK_URL)
QLIK_UZERINE_YAZ = _bool("QLIK_UZERINE_YAZ", True)
# Qlik'e hep ayni adla yuklensin (uzerine yazilir, birikmez). Bos: kaynak dosyanin adi (tarih oneki atilarak)
QLIK_DOSYA_ADI = (os.getenv("QLIK_DOSYA_ADI") or "").strip().strip("'\"")
QLIK_TARIHSIZ = _bool("QLIK_TARIHSIZ", True)      # 20261028_APK_Rapor.pdf -> APK_Rapor.mp4
QLIK_SRT = _bool("QLIK_SRT", False)
# Qlik'e ayni adla gonderilecek dosyalar: video (.mp4), pdf (kaynak PDF), ses (videonun sesi), srt (altyazi)
QLIK_YUKLENECEKLER = [t.strip().lower() for t in
                      (os.getenv("QLIK_YUKLENECEKLER") or "video,pdf,ses").replace(";", ",").split(",")
                      if t.strip()]
if QLIK_SRT and "srt" not in QLIK_YUKLENECEKLER:
    QLIK_YUKLENECEKLER.append("srt")
for _t in QLIK_YUKLENECEKLER:
    if _t not in ("video", "pdf", "ses", "srt"):
        UYARILAR.append(f"QLIK_YUKLENECEKLER: '{_t}' tanınmadı (geçerli: video, pdf, ses, srt).")
QLIK_SES_FORMATI = (os.getenv("QLIK_SES_FORMATI") or "mp3").strip().lower().lstrip(".")   # mp3 | m4a | wav
try:
    QLIK_TIMEOUT = float(os.getenv("QLIK_TIMEOUT", "600"))
except ValueError:
    QLIK_TIMEOUT = 600.0
IZLE_QLIK = _bool("IZLE_QLIK", False)   # izleyici videoyu olusturduktan sonra Qlik'e yuklesin
QLIK_NOTLAR: list[str] = []             # adres cozumlemesi gibi bilgiler (arayuzde gosterilir)


def _qlik_icerik_adresini_coz():
    """QLIK_URL'ye izleme (content library) adresi yazildiysa ayiklar:
    https://sunucu/content/Kutuphane  ->  kutuphane=Kutuphane, izleme koku=https://sunucu,
    yukleme (QRS) adresi: sertifika -> https://sunucu:4242, header -> https://sunucu"""
    global QLIK_URL, QLIK_KUTUPHANE, QLIK_ICERIK_URL
    from urllib.parse import unquote, urlsplit

    if "/content/" not in QLIK_URL.lower():
        return
    p = urlsplit(QLIK_URL)
    i = p.path.lower().index("/content/")
    onek = p.path[:i]                                   # virtual proxy oneki olabilir (/vp)
    kutuphane = unquote(p.path[i + len("/content/"):].strip("/").split("/")[0])
    kok = f"{p.scheme}://{p.netloc}{onek}"
    if kutuphane and not os.getenv("QLIK_KUTUPHANE"):
        QLIK_KUTUPHANE = kutuphane
    elif kutuphane and kutuphane != QLIK_KUTUPHANE:
        UYARILAR.append(f"QLIK_URL içindeki kütüphane ({kutuphane}) QLIK_KUTUPHANE ({QLIK_KUTUPHANE}) "
                        "ile farklı; QLIK_KUTUPHANE kullanılıyor.")
    if not QLIK_ICERIK_URL:
        QLIK_ICERIK_URL = kok
    if QLIK_KIMLIK == "sertifika":
        QLIK_URL = f"{p.scheme}://{p.hostname}:4242"
    else:
        QLIK_URL = kok
    QLIK_NOTLAR.append(
        f"QLIK_URL bir izleme adresi; şöyle yorumlandı → kütüphane: {QLIK_KUTUPHANE}, "
        f"yükleme adresi: {QLIK_URL}, izleme adresi: {QLIK_ICERIK_URL}/content/{QLIK_KUTUPHANE}/…  "
        "Qlik ekibi farklı bir yükleme (QRS) adresi verdiyse QLIK_URL'ye onu yazın.")


_qlik_icerik_adresini_coz()
