"""
DocVoice klasor izleyici: klasore dusen PDF'leri otomatik olarak videoya cevirir.

Calistirma:
    python izleyici.py              surekli izler (durdurmak icin Ctrl + C)
    python izleyici.py --bir-kez    klasordeki mevcut PDF'leri isler ve cikar

Ayarlar (.env):
    IZLE_KLASORU        yeni PDF'lerin dusecegi klasor
    IZLE_HEDEF_KLASORU  videolarin aktarilacagi klasor
    IZLE_ARALIK         kontrol araligi (sn, varsayilan 10)
    VIDEO_SUNUM / VIDEO_ALTYAZI  arayuzdeki secenekler gibi

Izlenen klasorde olusan alt klasorler:
    isleniyor/   o an islenen PDF
    islenen/     basariyla videoya cevrilen PDF'ler
    hatali/      islenemeyen PDF'ler (yaninda .hata.txt aciklamasi)
"""
import argparse
import hashlib
import json
import logging
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import config
from services.llm_client import LLMHatasi, sayfalari_formatla
from services.pdf_pages import sayfa_metinleri
from services.ssml_tools import ssml_onar
from services.tts_client import TTSHatasi
from services.video_builder import VideoHatasi, pdf_videosu_olustur

ISLENIYOR, ISLENEN, HATALI = "isleniyor", "islenen", "hatali"
log = logging.getLogger("docvoice.izleyici")


# ------------------------------------------------------------------ kurulum
def _log_ayarla():
    klasor = config.PROJE_KLASORU / "logs"
    klasor.mkdir(exist_ok=True)
    bicim = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    dosya = logging.FileHandler(klasor / "izleyici.log", encoding="utf-8")
    dosya.setFormatter(bicim)
    ekran = logging.StreamHandler(sys.stdout)
    ekran.setFormatter(bicim)
    log.handlers[:] = [dosya, ekran]
    log.setLevel(logging.INFO)


def _ayarlari_dogrula() -> list[str]:
    hatalar = []
    if not config.IZLE_KLASORU:
        hatalar.append("IZLE_KLASORU tanımlı değil (.env)")
    elif not config.IZLE_KLASORU.is_dir():
        hatalar.append(f"İzlenecek klasör bulunamadı: {config.IZLE_KLASORU}")
    if not config.IZLE_HEDEF_KLASORU:
        hatalar.append("IZLE_HEDEF_KLASORU tanımlı değil (.env)")
    if not config.LLM_URL:
        hatalar.append("LLM_URL tanımlı değil (.env)")
    if not config.TTS_URL:
        hatalar.append("TTS_URL tanımlı değil (.env)")
    if not _kurallar_dosyasi().exists():
        hatalar.append(f"Kural seti dosyası bulunamadı: {_kurallar_dosyasi()}")
    return hatalar + [u for u in config.UYARILAR if "IZLE" in u]


def _kurallar_dosyasi() -> Path:
    return config.IZLE_KURALLAR or config.KURALLAR_DOSYASI


# ----------------------------------------------------------------- yardimci
def _benzersiz(hedef: Path) -> Path:
    """Ayni adda dosya varsa sonuna zaman damgasi ekler."""
    if not hedef.exists():
        return hedef
    return hedef.with_name(f"{hedef.stem}_{datetime.now():%Y%m%d_%H%M%S}{hedef.suffix}")


def _tasi(kaynak: Path, klasor: Path) -> Path:
    klasor.mkdir(parents=True, exist_ok=True)
    hedef = _benzersiz(klasor / kaynak.name)
    shutil.move(str(kaynak), str(hedef))
    return hedef


def _yeni_pdfler(klasor: Path) -> list[Path]:
    return sorted(
        (p for p in klasor.iterdir()
         if p.is_file() and p.suffix.lower() == ".pdf" and not p.name.startswith(("~$", "."))),
        key=lambda p: p.stat().st_mtime,
    )


def _pdf_tamam_mi(yol: Path) -> bool:
    """Tam bir PDF dosyasi son kisminda %%EOF isareti tasir; yarim kopyada bu yoktur."""
    try:
        with open(yol, "rb") as f:
            f.seek(max(0, yol.stat().st_size - 2048))
            return b"%%EOF" in f.read()
    except OSError:
        return False


class KopyalamaTakibi:
    """Dosya hala kopyalaniyorsa islemeye baslama:
    - boyut IZLE_BEKLEME sn boyunca sabit kalmali
    - dosya %%EOF ile bitmeli (ag kopyalarinda duraksamalara karsi);
      10 dk boyunca tamamlanmazsa yine de islenir ve hata klasorune duser
    """
    AZAMI_BEKLEME = 600

    def __init__(self):
        self.gorulen: dict[Path, tuple[int, float]] = {}
        self.ilk_gorulme: dict[Path, float] = {}

    def hazir_mi(self, yol: Path) -> bool:
        try:
            boyut = yol.stat().st_size
        except OSError:
            return False
        simdi = time.monotonic()
        self.ilk_gorulme.setdefault(yol, simdi)
        onceki = self.gorulen.get(yol)
        if onceki is None or onceki[0] != boyut or boyut == 0:
            self.gorulen[yol] = (boyut, simdi)
            return False
        if simdi - onceki[1] < config.IZLE_BEKLEME:
            return False
        if not _pdf_tamam_mi(yol) and simdi - self.ilk_gorulme[yol] < self.AZAMI_BEKLEME:
            return False
        try:   # Windows'ta baska program dosyayi aciksa yeniden adlandirma basarisiz olur
            yol.rename(yol)
        except OSError:
            return False
        self.gorulen.pop(yol, None)
        self.ilk_gorulme.pop(yol, None)
        return True


def _llm_onbellekli(kurallar: str, metinler: list[str]) -> list[str]:
    """Ayni PDF tekrar islenirse (hata sonrasi gibi) LLM sonuclarini yeniden istemez."""
    anahtar = hashlib.sha256(json.dumps([kurallar, metinler], ensure_ascii=False).encode()).hexdigest()
    dosya = config.CIKTI_KLASORU / ".llm_cache" / f"{anahtar}.json"
    if dosya.exists():
        log.info("  LLM sonuçları önbellekten alındı")
        return json.loads(dosya.read_text(encoding="utf-8"))

    def ilerleme(biten, toplam):
        log.info(f"  LLM: {biten} / {toplam} sayfa hazır")

    sonuc = sayfalari_formatla(kurallar, metinler, ilerleme=ilerleme)
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_text(json.dumps(sonuc, ensure_ascii=False), encoding="utf-8")
    return sonuc


# --------------------------------------------------------------- isleme
def pdf_isle(pdf_yolu: Path) -> Path:
    """Tek bir PDF'i videoya cevirir, videoyu hedef klasore koyar. Doner: video yolu."""
    baslangic = time.monotonic()
    veri = pdf_yolu.read_bytes()
    metinler = sayfa_metinleri(veri)
    log.info(f"  {len(metinler)} sayfa, metin içeren: {sum(1 for m in metinler if m.strip())}")
    if not any(m.strip() for m in metinler):
        raise VideoHatasi("PDF'te okunabilir metin yok (taranmış belge olabilir).")

    kurallar = _kurallar_dosyasi().read_text(encoding="utf-8")
    sayfa_ssml = []
    for i, ssml in enumerate(_llm_onbellekli(kurallar, metinler)):
        if ssml.strip():
            ssml, onarildi = ssml_onar(ssml)
            if onarildi:
                log.info(f"  Sayfa {i + 1}: hatalı SSML etiketleri düzeltildi")
        sayfa_ssml.append(ssml)

    son_adim = [""]

    def ilerleme(oran, mesaj):
        # Her mesaji degil, adim degisimlerini yaz
        adim = mesaj.split(":")[0]
        if adim != son_adim[0]:
            son_adim[0] = adim
            log.info(f"  {mesaj}")

    sonuc = pdf_videosu_olustur(veri, sayfa_ssml, ilerleme=ilerleme,
                                altyazi=config.VIDEO_ALTYAZI, sunum=config.VIDEO_SUNUM)

    hedef_klasor = config.IZLE_HEDEF_KLASORU
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    video = _benzersiz(hedef_klasor / f"{pdf_yolu.stem}.mp4")
    shutil.move(str(sonuc.video), str(video))
    if config.IZLE_SRT:
        shutil.move(str(sonuc.altyazi), str(video.with_suffix(".srt")))
    else:
        sonuc.altyazi.unlink(missing_ok=True)

    sure = time.monotonic() - baslangic
    log.info(f"  Video: {video}  ({int(sonuc.sure // 60)} dk {int(sonuc.sure % 60)} sn, "
             f"işlem {int(sure // 60)} dk {int(sure % 60)} sn)")
    return video


def bir_tur(klasor: Path, takip: KopyalamaTakibi) -> int:
    islenen = 0
    for pdf in _yeni_pdfler(klasor):
        if not takip.hazir_mi(pdf):
            continue
        log.info(f"Yeni PDF: {pdf.name}")
        calisma = _tasi(pdf, klasor / ISLENIYOR)
        try:
            pdf_isle(calisma)
            _tasi(calisma, klasor / ISLENEN)
            islenen += 1
        except (LLMHatasi, TTSHatasi, VideoHatasi, ValueError) as e:
            _hata_kaydet(calisma, klasor, str(e))
        except Exception as e:   # beklenmeyen hata: izleyici durmasin
            _hata_kaydet(calisma, klasor, f"{e}\n\n{traceback.format_exc()}")
    return islenen


def _hata_kaydet(pdf: Path, klasor: Path, mesaj: str):
    hedef = _tasi(pdf, klasor / HATALI)
    hedef.with_suffix(".hata.txt").write_text(
        f"{datetime.now():%Y-%m-%d %H:%M:%S}\n{pdf.name}\n\n{mesaj}\n\n"
        "Yeniden denemek için PDF'i ana klasöre geri taşıyın. "
        "Başarılı seslendirme ve LLM sonuçları önbellekte, tekrar istenmez.\n",
        encoding="utf-8",
    )
    log.error(f"  HATA: {mesaj.splitlines()[0]}  -> {HATALI}/{hedef.name}")


def _yarim_kalanlari_geri_al(klasor: Path):
    """Onceki calisma yarida kesildiyse (bilgisayar kapandi vb.) PDF'i yeniden kuyruga al."""
    yarim = klasor / ISLENIYOR
    if yarim.is_dir():
        for p in yarim.iterdir():
            if p.suffix.lower() == ".pdf":
                _tasi(p, klasor)
                log.info(f"Yarım kalan PDF yeniden kuyruğa alındı: {p.name}")


def main():
    ap = argparse.ArgumentParser(description="DocVoice klasör izleyici")
    ap.add_argument("--bir-kez", action="store_true", help="mevcut PDF'leri işle ve çık")
    args = ap.parse_args()

    _log_ayarla()
    hatalar = _ayarlari_dogrula()
    if hatalar:
        for h in hatalar:
            log.error(h)
        sys.exit(1)

    klasor = config.IZLE_KLASORU
    log.info("DocVoice izleyici başladı")
    log.info(f"  İzlenen klasör : {klasor}")
    log.info(f"  Hedef klasör   : {config.IZLE_HEDEF_KLASORU}")
    log.info(f"  Kural seti     : {_kurallar_dosyasi()}")
    log.info(f"  Sunum görünümü : {'açık' if config.VIDEO_SUNUM else 'kapalı'} · "
             f"Altyazı: {'açık' if config.VIDEO_ALTYAZI else 'kapalı'}")
    _yarim_kalanlari_geri_al(klasor)

    takip = KopyalamaTakibi()
    try:
        if args.bir_kez:
            # Kopyalama kontrolu icin dosyalari iki kez gormek gerekir
            bir_tur(klasor, takip)
            time.sleep(config.IZLE_BEKLEME + 0.5)
            n = bir_tur(klasor, takip)
            log.info(f"Tamamlandı ({n} PDF işlendi)")
            return
        log.info(f"Her {config.IZLE_ARALIK:g} sn'de bir kontrol ediliyor. Durdurmak için Ctrl + C")
        while True:
            try:
                bir_tur(klasor, takip)
            except OSError as e:   # ag paylasimi gecici olarak erisilemez olabilir
                log.warning(f"Klasöre erişilemedi, tekrar denenecek: {e}")
            time.sleep(config.IZLE_ARALIK)
    except KeyboardInterrupt:
        log.info("İzleyici durduruldu")


if __name__ == "__main__":
    main()
