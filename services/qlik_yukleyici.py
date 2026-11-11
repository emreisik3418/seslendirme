"""Videoyu Qlik Sense (sirket ici) content library'sine QRS API ile yukler.

Akis:  POST {QLIK_URL}/qrs/contentlibrary/{kutuphane}/uploadfile?externalpath=<dosya>&overwrite=true
       Dosya adi her seferinde ayni (yukleme_adi): eski dosyalar uzerine yazilir, kutuphanede birikme olmaz.
       QLIK_YUKLENECEKLER ile video, kaynak PDF, ses (mp3) ve altyazi ayni adla gonderilir.
Sonuc: video {QLIK_ICERIK_URL}/content/{kutuphane}/<dosya> adresinden izlenir
       (uygulamada Dashboard bundle > Video player nesnesine bu adres verilir).

Kimlik dogrulama (QLIK_KIMLIK):
  sertifika  Qlik'ten disa aktarilan client.pem + client_key.pem; dogrudan QRS'e (genelde 4242 portu).
             QLIK_KULLANICI: "UserDirectory=INTERNAL; UserId=sa_repository" gibi.
  header     Header ile kimlik dogrulayan bir virtual proxy uzerinden (QLIK_URL proxy onekini icerir).
             QLIK_KULLANICI: "DOMAIN\\kullanici", header adi QLIK_HEADER_ADI.

QRS her istekte ayni 16 karakterlik xrfkey'i hem sorguda hem X-Qlik-Xrfkey header'inda ister.
"""
import mimetypes
import re
import secrets
import ssl
import string
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

import config


class QlikHatasi(Exception):
    pass


@dataclass
class YuklemeSonucu:
    dosya: str
    adres: str          # videonun izlenecegi adres
    yol: str            # kutuphane icindeki mantiksal yol (/content/...)


def tanimli_mi() -> bool:
    return bool(config.QLIK_URL and config.QLIK_KUTUPHANE)


def _xrfkey() -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))


def _ssl_baglami():
    """Qlik'in kendi kok sertifikasi (root.pem) ve istemci sertifikasi icin SSL ayari."""
    if not config.QLIK_SSL_DOGRULA and config.QLIK_KIMLIK != "sertifika":
        return False
    if config.QLIK_KIMLIK != "sertifika" and not config.QLIK_KOK_SERTIFIKA:
        return config.ssl_dogrulama()     # header modu: sirket sertifikasi (Windows deposu) yeterli
    # truststore'un degistirmedigi orijinal SSLContext: root.pem ile dogrulama yapabilmek icin
    ctx = config.ORIJINAL_SSLCONTEXT(ssl.PROTOCOL_TLS_CLIENT)
    if config.QLIK_SSL_DOGRULA:
        if config.QLIK_KOK_SERTIFIKA:
            ctx.load_verify_locations(cafile=str(config.QLIK_KOK_SERTIFIKA))
        else:
            ctx.load_default_certs()
        ctx.check_hostname = config.QLIK_HOST_KONTROL
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if config.QLIK_KIMLIK == "sertifika":
        if not (config.QLIK_SERTIFIKA and config.QLIK_ANAHTAR):
            raise QlikHatasi("Sertifika ile bağlantı için QLIK_SERTIFIKA (client.pem) ve "
                             "QLIK_ANAHTAR (client_key.pem) tanımlanmalı.")
        for ad, yol in (("QLIK_SERTIFIKA", config.QLIK_SERTIFIKA), ("QLIK_ANAHTAR", config.QLIK_ANAHTAR)):
            if not Path(yol).exists():
                raise QlikHatasi(f"{ad} dosyası bulunamadı: {yol}")
        ctx.load_cert_chain(certfile=str(config.QLIK_SERTIFIKA), keyfile=str(config.QLIK_ANAHTAR))
    return ctx


def _headerlar(xrf: str, icerik_turu: str | None = None) -> dict:
    h = {"X-Qlik-Xrfkey": xrf}
    if config.QLIK_KIMLIK == "sertifika":
        h["X-Qlik-User"] = config.QLIK_KULLANICI or "UserDirectory=INTERNAL; UserId=sa_repository"
    elif config.QLIK_KULLANICI:
        h[config.QLIK_HEADER_ADI] = config.QLIK_KULLANICI
    if icerik_turu:
        h["Content-Type"] = icerik_turu
    return h


def _istemci() -> httpx.Client:
    if not tanimli_mi():
        raise QlikHatasi(".env dosyasında QLIK_URL tanımlı değil.")
    try:
        dogrula = _ssl_baglami()
    except ssl.SSLError as e:
        raise QlikHatasi(f"Sertifika dosyaları okunamadı: {e}") from e
    return httpx.Client(base_url=config.QLIK_URL, verify=dogrula, timeout=config.QLIK_TIMEOUT)


def _hata_mesaji(yanit: httpx.Response) -> str:
    ipucu = {
        401: "Kimlik doğrulanamadı: sertifika / kullanıcı bilgisini kontrol edin.",
        403: "Yetki yok: kullanıcının content library'ye yazma izni olmalı (Qlik güvenlik kuralları). "
             "Xrfkey hatası da 403 döner.",
        404: f"'{config.QLIK_KUTUPHANE}' adlı content library bulunamadı veya adres yanlış.",
        409: "Aynı adda dosya var (QLIK_UZERINE_YAZ=true ile üzerine yazılabilir).",
        413: "Dosya sunucunun (veya aradaki proxy'nin) izin verdiği boyuttan büyük.",
    }.get(yanit.status_code, "")
    return f"HTTP {yanit.status_code}: {ipucu} {yanit.text[:300]}".strip()


def baglanti_testi() -> str:
    """Sunucuya ulasilabildigini ve kutuphanenin var oldugunu kontrol eder. Doner: aciklama."""
    xrf = _xrfkey()
    try:
        with _istemci() as c:
            y = c.get("/qrs/about", params={"xrfkey": xrf}, headers=_headerlar(xrf))
            if y.status_code != 200:
                raise QlikHatasi(_hata_mesaji(y))
            surum = y.json().get("buildVersion", "?")
            filtre = f"name eq '{config.QLIK_KUTUPHANE}'"
            y = c.get("/qrs/contentlibrary", params={"xrfkey": xrf, "filter": filtre},
                      headers=_headerlar(xrf))
            if y.status_code != 200:
                raise QlikHatasi(_hata_mesaji(y))
            if not y.json():
                raise QlikHatasi(f"Sunucuya bağlanıldı (sürüm {surum}) ama '{config.QLIK_KUTUPHANE}' "
                                 "adlı content library yok. Qlik ekibinden oluşturmasını isteyin.")
    except httpx.ConnectError as e:
        raise QlikHatasi(f"Qlik sunucusuna bağlanılamadı (ağ / port / SSL): {e}") from e
    except httpx.TimeoutException as e:
        raise QlikHatasi("Qlik sunucusu zaman aşımına uğradı.") from e
    return f"Bağlantı başarılı · Qlik sürüm {surum} · kütüphane '{config.QLIK_KUTUPHANE}' bulundu"


def yukle(dosya: Path, ad: str | None = None, deneme: int = 3) -> YuklemeSonucu:
    """Dosyayi content library'ye yukler (gecici hatalarda tekrar dener)."""
    dosya = Path(dosya)
    if not dosya.exists():
        raise QlikHatasi(f"Yüklenecek dosya bulunamadı: {dosya}")
    ad = ad or dosya.name
    tur = mimetypes.guess_type(ad)[0] or ("text/plain" if ad.lower().endswith(".srt") else "application/octet-stream")
    son_hata = ""
    for i in range(1, deneme + 1):
        xrf = _xrfkey()
        try:
            with _istemci() as c, open(dosya, "rb") as f:
                y = c.post(
                    f"/qrs/contentlibrary/{quote(config.QLIK_KUTUPHANE, safe='')}/uploadfile",
                    params={"externalpath": ad, "overwrite": str(config.QLIK_UZERINE_YAZ).lower(),
                            "xrfkey": xrf},
                    headers=_headerlar(xrf, tur),
                    content=f,     # dosya parca parca gonderilir, bellege tamamen alinmaz
                )
        except httpx.ConnectError as e:
            son_hata = f"Qlik sunucusuna bağlanılamadı: {e}"
        except httpx.TimeoutException:
            son_hata = f"Yükleme {config.QLIK_TIMEOUT:.0f} sn içinde tamamlanmadı."
        else:
            if y.status_code in (200, 201):
                yol = ""
                try:
                    yol = y.json().get("logicalPath", "") if y.content else ""
                except ValueError:
                    pass
                yol = yol or f"/content/{config.QLIK_KUTUPHANE}/{ad}"
                kok = config.QLIK_ICERIK_URL or config.QLIK_URL
                return YuklemeSonucu(dosya=ad, adres=kok + quote(yol, safe="/"), yol=yol)
            son_hata = _hata_mesaji(y)
            if y.status_code not in (429, 500, 502, 503, 504):
                raise QlikHatasi(son_hata)
        if i < deneme:
            time.sleep(min(2 ** i, 20))
    raise QlikHatasi(f"{son_hata} ({deneme} deneme yapıldı)")


# ------------------------------------------------------------ dosya adi
# Dosya adinin basindaki tarih (NPrinting vb.): 20261028_, 2026-10-28 , 28.10.2026-, 20261028_1015_ ...
_TARIH_ONEKI = re.compile(
    r"^(?:\d{4}[-_.]?\d{2}[-_.]?\d{2}|\d{2}[-_.]?\d{2}[-_.]?\d{4})"   # yyyymmdd / ddmmyyyy
    r"(?:[-_ .T]?\d{2}[-_.:]?\d{2}(?:[-_.:]?\d{2})?)?"                  # istege bagli saat
    r"[\s_\-.]+"
)
_ZAMAN_SONEKI = re.compile(r"_\d{8}_\d{6}$")          # ayni ad varken eklenen _20261028_101500
_URL_BOZAN = re.compile(r"[\s#?%&+\\/:*\"<>|']+")    # adreste sorun cikaran karakterler


def tarihsiz_ad(ad: str) -> str:
    """'20261028_APK_Rapor' -> 'APK_Rapor'. Tarih oneki yoksa adi aynen dondurur."""
    kalan = _TARIH_ONEKI.sub("", ad, count=1)
    return kalan or ad


def yukleme_adi(kaynak: str | Path | None, uzanti: str = ".mp4") -> str:
    """Qlik'teki dosya adi. Ayni kaynaktan her gun ayni ad cikar, boylece dosya uzerine yazilir.
    Oncelik: QLIK_DOSYA_ADI > kaynak dosyanin adi (QLIK_TARIHSIZ ile tarih oneki atilir) > 'docvoice'."""
    if config.QLIK_DOSYA_ADI:
        kok = Path(config.QLIK_DOSYA_ADI).stem if Path(config.QLIK_DOSYA_ADI).suffix else config.QLIK_DOSYA_ADI
    else:
        kok = Path(str(kaynak or "")).stem
        kok = _ZAMAN_SONEKI.sub("", kok)
        if config.QLIK_TARIHSIZ:
            kok = tarihsiz_ad(kok)
    return temiz_ad(kok, uzanti) or "docvoice" + uzanti


def temiz_ad(ad: str, uzanti: str = ".mp4") -> str:
    """Adresi bozan karakterleri '_' yapar, uzantiyi ekler: 'APK Rapor' -> 'APK_Rapor.mp4'. Bos ad: ''"""
    kok = (ad or "").strip()
    for uz in {uzanti, ".mp4", ".pdf", ".mp3", ".m4a", ".wav", ".srt"}:
        if kok.lower().endswith(uz):
            kok = kok[: -len(uz)]
            break
    kok = _URL_BOZAN.sub("_", kok).strip("._-")
    return kok + uzanti if kok else ""


@dataclass
class TopluSonuc:
    yuklenenler: list          # YuklemeSonucu listesi (ilki varsa video)
    atlananlar: list           # gonderilemeyen ama hata sayilmayan dosyalar icin aciklama

    @property
    def video(self):
        return next((r for r in self.yuklenenler if r.dosya.lower().endswith(".mp4")), None)


def ses_cikar(video: Path, hedef: Path) -> Path:
    """Videonun ses kanalini ayri dosyaya yazar (mp3 / m4a / wav). Doner: yazilan dosya."""
    from services.video_builder import VideoHatasi, _calistir, ffmpeg_yolu

    try:
        ffmpeg = ffmpeg_yolu()
    except VideoHatasi as e:
        raise QlikHatasi(str(e)) from e
    secenek = {
        ".mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
        ".m4a": ["-c:a", "copy"],                     # videodaki AAC sesi yeniden kodlamadan
        ".wav": ["-c:a", "pcm_s16le"],
    }.get(hedef.suffix.lower(), ["-c:a", "libmp3lame", "-b:a", "128k"])
    try:
        _calistir([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-vn", *secenek, str(hedef)])
    except VideoHatasi as e:
        if hedef.suffix.lower() == ".m4a":
            raise QlikHatasi(f"Videodan ses çıkarılamadı: {e}") from e
        # FFmpeg'de mp3 kodlayici yoksa: sesi kopyalayarak m4a yap
        yedek = hedef.with_suffix(".m4a")
        try:
            _calistir([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-vn", "-c:a", "copy", str(yedek)])
        except VideoHatasi as e2:
            raise QlikHatasi(f"Videodan ses çıkarılamadı: {e2}") from e2
        return yedek
    return hedef


def dosyalari_yukle(video: Path, altyazi: Path | None = None, pdf: Path | bytes | None = None,
                    kaynak_adi: str | None = None, ad: str | None = None,
                    turler: list[str] | None = None) -> TopluSonuc:
    """Videoyu ve QLIK_YUKLENECEKLER'deki diger dosyalari AYNI adla yukler:
    APKO_Yonetici_Ozeti.mp4 / .pdf / .mp3 (/ .srt). Ayni adli eski dosyalarin uzerine yazilir.
    pdf: dosya yolu veya PDF'in icerigi (bytes)."""
    import tempfile

    video = Path(video)
    kok = Path(ad or yukleme_adi(kaynak_adi or video.name)).stem
    turler = [t.lower() for t in (turler if turler is not None else config.QLIK_YUKLENECEKLER)]
    sonuc = TopluSonuc([], [])
    with tempfile.TemporaryDirectory(prefix="docvoice_qlik_") as gecici:
        gecici = Path(gecici)
        if "video" in turler:
            sonuc.yuklenenler.append(yukle(video, ad=f"{kok}.mp4"))
        if "pdf" in turler:
            if isinstance(pdf, (bytes, bytearray)):
                yol = gecici / f"{kok}.pdf"
                yol.write_bytes(pdf)
                pdf = yol
            if pdf and Path(pdf).exists():
                sonuc.yuklenenler.append(yukle(Path(pdf), ad=f"{kok}.pdf"))
            else:
                sonuc.atlananlar.append("PDF gönderilmedi: bu video bir PDF'ten üretilmedi.")
        if "ses" in turler:
            ses = ses_cikar(video, gecici / f"{kok}.{config.QLIK_SES_FORMATI}")
            sonuc.yuklenenler.append(yukle(ses, ad=ses.name))
        if "srt" in turler:
            if altyazi and Path(altyazi).exists():
                sonuc.yuklenenler.append(yukle(Path(altyazi), ad=f"{kok}.srt"))
            else:
                sonuc.atlananlar.append("Altyazı (.srt) bulunamadı, gönderilmedi.")
    return sonuc


def video_yukle(video: Path, altyazi: Path | None = None, kaynak_adi: str | None = None,
                ad: str | None = None) -> YuklemeSonucu:
    """Geriye uyumluluk: sadece video (+ QLIK_SRT acikken altyazi). Doner: videonun sonucu."""
    turler = ["video"] + (["srt"] if config.QLIK_SRT else [])
    return dosyalari_yukle(video, altyazi, kaynak_adi=kaynak_adi, ad=ad, turler=turler).video
