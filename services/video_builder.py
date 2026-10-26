"""SSML icerikten slaytli + altyazili MP4 video uretir.

Akis:
  1) SSML <break> noktalarindan bolumlere ayrilir
  2) Her bolum ayri seslendirilir -> bolum suresi kesin bilinir
  3) Her bolum icin bir slayt, her cumle icin altyazili bir kare cizilir
  4) Sesler birlestirilir, kareler sureleriyle FFmpeg'e verilir -> MP4 + SRT
"""
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
from services.ssml_tools import Bolum, bolumlere_ayir
from services.tts_client import TTSHatasi, seslendir

GENISLIK, YUKSEKLIK = 1920, 1080
KENAR = 140


class VideoHatasi(Exception):
    pass


@dataclass
class VideoSonucu:
    video: Path
    altyazi: Path
    sure: float
    bolum_sayisi: int


# ----------------------------------------------------------------- yardimcilar
def ffmpeg_yolu() -> str:
    if config.VIDEO_FFMPEG:
        return config.VIDEO_FFMPEG
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    yol = shutil.which("ffmpeg")
    if yol:
        return yol
    raise VideoHatasi("FFmpeg bulunamadi. Kurmak icin: pip install imageio-ffmpeg")


def _calistir(komut: list[str]) -> None:
    sonuc = subprocess.run(komut, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if sonuc.returncode != 0:
        raise VideoHatasi(f"FFmpeg hatasi:\n{sonuc.stderr[-1500:]}")


def _font(kalin: bool, boyut: int) -> ImageFont.FreeTypeFont:
    adaylar = []
    if config.VIDEO_FONT_BOLD and kalin:
        adaylar.append(config.VIDEO_FONT_BOLD)
    if config.VIDEO_FONT and not kalin:
        adaylar.append(config.VIDEO_FONT)
    if kalin:
        adaylar += ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]
    else:
        adaylar += ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"]
    for yol in adaylar:
        try:
            return ImageFont.truetype(yol, boyut)
        except OSError:
            continue
    return ImageFont.load_default(boyut)


def _renk(hex_kod: str) -> tuple[int, int, int]:
    h = hex_kod.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _sar(metin: str, font, genislik: int, azami_satir: int) -> list[str]:
    """Metni piksel genisligine gore satirlara boler."""
    satirlar, satir = [], ""
    for kelime in metin.split():
        aday = f"{satir} {kelime}".strip()
        if font.getlength(aday) <= genislik or not satir:
            satir = aday
        else:
            satirlar.append(satir)
            satir = kelime
    if satir:
        satirlar.append(satir)
    if len(satirlar) > azami_satir:
        satirlar = satirlar[:azami_satir]
        son = satirlar[-1]
        while font.getlength(son + " …") > genislik and " " in son:
            son = son.rsplit(" ", 1)[0]
        satirlar[-1] = son + " …"
    return satirlar


def _tr_buyuk(metin: str) -> str:
    """Turkce buyuk harf: i -> İ, ı -> I"""
    return metin.replace("i", "İ").replace("ı", "I").upper()


def _baslik(bolum: Bolum) -> str:
    return bolum.baslik or bolum.metin


# ------------------------------------------------------------------- cizim
def _arka_plan() -> Image.Image:
    ust, alt = _renk(config.VIDEO_BG), _renk(config.VIDEO_BG2)
    img = Image.new("RGB", (GENISLIK, YUKSEKLIK), ust)
    d = ImageDraw.Draw(img)
    for y in range(YUKSEKLIK):
        t = y / YUKSEKLIK
        d.line([(0, y), (GENISLIK, y)], fill=tuple(int(ust[i] + (alt[i] - ust[i]) * t) for i in range(3)))
    return img


def _logo_ekle(img: Image.Image) -> int:
    """Logo varsa sol uste koyar, logodan sonraki x konumunu dondurur."""
    if not config.VIDEO_LOGO or not Path(config.VIDEO_LOGO).exists():
        return KENAR
    logo = Image.open(config.VIDEO_LOGO).convert("RGBA")
    logo.thumbnail((260, 70))
    img.paste(logo, (KENAR, 60 + (70 - logo.height) // 2), logo)
    return KENAR + logo.width + 30


def slayt_ciz(bolum: Bolum, sira: int, toplam: int, belge_basligi: str) -> Image.Image:
    vurgu = _renk(config.VIDEO_ACCENT)
    img = _arka_plan()
    d = ImageDraw.Draw(img)

    # Ust bilgi: logo + belge basligi + sayac
    x = _logo_ekle(img)
    kucuk = _font(True, 26)
    d.text((x, 80), _tr_buyuk(belge_basligi)[:70], font=kucuk, fill=vurgu)
    sayac = f"{sira:02d} / {toplam:02d}"
    d.text((GENISLIK - KENAR - kucuk.getlength(sayac), 80), sayac, font=kucuk, fill=(200, 210, 225))
    d.line([(KENAR, 135), (GENISLIK - KENAR, 135)], fill=(70, 90, 120), width=2)

    # Arka planda buyuk, soluk bolum numarasi
    filigran = _font(True, 420)
    d.text((GENISLIK - KENAR - filigran.getlength(f"{sira:02d}"), 150), f"{sira:02d}",
           font=filigran, fill=tuple(min(255, c + 7) for c in _renk(config.VIDEO_BG2)))

    # Baslik
    kapak = sira == 1
    font = _font(True, 92 if kapak else 72)
    satirlar = _sar(_baslik(bolum), font, GENISLIK - 2 * KENAR - 60, 3 if kapak else 4)
    satir_y = int(font.size * 1.22)
    blok = satir_y * len(satirlar)
    y0 = (YUKSEKLIK - 260 - blok) // 2 + 120
    d.rectangle([KENAR, y0 + 8, KENAR + 10, y0 + blok - 14], fill=vurgu)
    for i, s in enumerate(satirlar):
        d.text((KENAR + 50, y0 + i * satir_y), s, font=font, fill=(255, 255, 255))
    return img


def altyazi_ekle(slayt: Image.Image, metin: str, ilerleme: float) -> Image.Image:
    img = slayt.copy().convert("RGBA")
    katman = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(katman)

    font = _font(False, 42)
    satirlar = _sar(metin, font, 1500, 2) if metin.strip() else []
    satir_y = 58
    if satirlar:
        kutu_y = len(satirlar) * satir_y + 44
        genis = max(font.getlength(s) for s in satirlar) + 80
        x0 = (GENISLIK - genis) / 2
        y0 = YUKSEKLIK - 70 - kutu_y
        d.rounded_rectangle([x0, y0, x0 + genis, y0 + kutu_y], radius=18, fill=(0, 0, 0, 170))
        for i, s in enumerate(satirlar):
            d.text(((GENISLIK - font.getlength(s)) / 2, y0 + 22 + i * satir_y), s,
                   font=font, fill=(255, 255, 255))

    # En altta ilerleme cubugu
    d.rectangle([0, YUKSEKLIK - 8, GENISLIK, YUKSEKLIK], fill=(255, 255, 255, 30))
    d.rectangle([0, YUKSEKLIK - 8, int(GENISLIK * ilerleme), YUKSEKLIK], fill=_renk(config.VIDEO_ACCENT) + (255,))
    return Image.alpha_composite(img, katman).convert("RGB")


# -------------------------------------------------------------------- ses
def _wav_yap(ffmpeg: str, girdi: Path, cikti: Path) -> float:
    _calistir([ffmpeg, "-y", "-loglevel", "error", "-i", str(girdi),
               "-ar", "24000", "-ac", "1", "-sample_fmt", "s16", str(cikti)])
    with wave.open(str(cikti), "rb") as w:
        return w.getnframes() / w.getframerate()


def _wav_birlestir(parcalar: list[Path], cikti: Path) -> None:
    with wave.open(str(cikti), "wb") as hedef:
        for i, p in enumerate(parcalar):
            with wave.open(str(p), "rb") as kaynak:
                if i == 0:
                    hedef.setparams(kaynak.getparams())
                hedef.writeframes(kaynak.readframes(kaynak.getnframes()))


def _srt_zaman(sn: float) -> str:
    ms = int(round(sn * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


# ------------------------------------------------------------- PDF zemini
SAYFA_ALANI_ALT = YUKSEKLIK - 250   # sayfa gorseli bu cizginin ustunde kalir, altyazi altta


def sayfa_zemini(sayfa: Image.Image, sira: int, toplam: int) -> Image.Image:
    """PDF sayfasini ortalar; arkada sayfanin bulanik, karartilmis hali olur."""
    from PIL import ImageEnhance, ImageFilter

    zemin = sayfa.copy()
    oran = max(GENISLIK / zemin.width, YUKSEKLIK / zemin.height)
    zemin = zemin.resize((int(zemin.width * oran), int(zemin.height * oran)))
    x = (zemin.width - GENISLIK) // 2
    y = (zemin.height - YUKSEKLIK) // 2
    zemin = zemin.crop((x, y, x + GENISLIK, y + YUKSEKLIK)).filter(ImageFilter.GaussianBlur(40))
    zemin = ImageEnhance.Brightness(zemin).enhance(0.6)
    zemin = Image.blend(_arka_plan(), zemin, 0.22)   # kurumsal zemin + sayfanin soluk izi

    alan_w, alan_h = GENISLIK - 120, SAYFA_ALANI_ALT - 40
    on = sayfa.copy()
    on.thumbnail((alan_w, alan_h), Image.LANCZOS)
    px, py = (GENISLIK - on.width) // 2, 30 + (alan_h - on.height) // 2

    golge = Image.new("RGBA", (on.width + 40, on.height + 40), (0, 0, 0, 0))
    ImageDraw.Draw(golge).rectangle([20, 20, on.width + 20, on.height + 20], fill=(0, 0, 0, 150))
    golge = golge.filter(ImageFilter.GaussianBlur(14))
    zemin = zemin.convert("RGBA")
    zemin.alpha_composite(golge, (px - 14, py - 8))
    zemin = zemin.convert("RGB")
    zemin.paste(on, (px, py))

    d = ImageDraw.Draw(zemin)
    font = _font(True, 26)
    etiket = f"Sayfa {sira} / {toplam}"
    w = font.getlength(etiket) + 36
    d.rounded_rectangle([GENISLIK - 40 - w, 30, GENISLIK - 40, 74], radius=10, fill=(0, 0, 0))
    d.text((GENISLIK - 40 - w + 18, 36), etiket, font=font, fill=(255, 255, 255))
    return zemin


# ---------------------------------------------------------------- ana akis
@dataclass
class Sahne:
    zemin: Image.Image
    bolumler: list           # list[Bolum]; bossa sahne sessiz gosterilir
    sessiz_sure: float = 3.0
    etiket: str = ""         # hata mesajlarinda kullanilir: "Sayfa 3", "Slayt 2"


def _sessiz_wav(yol: Path, sure: float) -> float:
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * sure))
    return sure


def _uret(sahneler: list[Sahne], ilerleme, on_ek: str) -> VideoSonucu:
    def bildir(oran, mesaj):
        if ilerleme:
            ilerleme(min(oran, 1.0), mesaj)

    ffmpeg = ffmpeg_yolu()
    toplam_bolum = sum(max(1, len(s.bolumler)) for s in sahneler)

    with tempfile.TemporaryDirectory(prefix="docvoice_") as gecici:
        tmp = Path(gecici)

        # 1) Seslendirme: her bolum ayri -> sureler kesin
        wavlar, plan, n = [], [], 0      # plan: (sahne_no, bolum|None, sure)
        for si, sahne in enumerate(sahneler):
            if not sahne.bolumler:
                n += 1
                wav = tmp / f"ses_{n:04d}.wav"
                plan.append((si, None, _sessiz_wav(wav, sahne.sessiz_sure)))
                wavlar.append(wav)
                continue
            for b in sahne.bolumler:
                n += 1
                bildir(0.6 * (n - 1) / toplam_bolum, f"Seslendiriliyor: {n} / {toplam_bolum}")
                try:
                    ses, _ = seslendir(f'{b.ssml}<break time="{b.ara_sure}"/>')
                except TTSHatasi as e:
                    yer = f"{sahne.etiket or f'Sahne {si + 1}'}, bölüm {sahne.bolumler.index(b) + 1}"
                    raise TTSHatasi(
                        f"{yer} seslendirilemedi: {e}\n\n"
                        f"Başarılı bölümler kaydedildi; tekrar denediğinizde sadece kalanlar istenir.\n\n"
                        f"Gönderilen metin:\n{b.ssml[:800]}"
                    ) from e
                ham = tmp / f"ses_{n:04d}.ham"
                ham.write_bytes(ses)
                wav = tmp / f"ses_{n:04d}.wav"
                plan.append((si, b, _wav_yap(ffmpeg, ham, wav)))
                wavlar.append(wav)

        tum_ses = tmp / "tum.wav"
        _wav_birlestir(wavlar, tum_ses)
        toplam_sure = sum(p[2] for p in plan) or 1

        # 2) Kareler
        bildir(0.65, "Kareler çiziliyor")
        kareler, srt, zaman, k = [], [], 0.0, 0
        for si, b, sure in plan:
            zemin = sahneler[si].zemin
            parcalar = (b.cumleler or [b.metin]) if b else []
            if not parcalar:
                k += 1
                ad = f"kare_{k:05d}.png"
                altyazi_ekle(zemin, "", zaman / toplam_sure).save(tmp / ad)
                kareler.append((ad, sure))
                zaman += sure
                continue
            harf = sum(len(p) for p in parcalar) or 1
            for p in parcalar:
                p_sure = sure * len(p) / harf
                k += 1
                ad = f"kare_{k:05d}.png"
                altyazi_ekle(zemin, p, zaman / toplam_sure).save(tmp / ad)
                kareler.append((ad, p_sure))
                srt.append(f"{len(srt) + 1}\n{_srt_zaman(zaman)} --> {_srt_zaman(zaman + p_sure)}\n{p}\n")
                zaman += p_sure

        liste = tmp / "liste.txt"
        satirlar = [f"file '{ad}'\nduration {s:.3f}" for ad, s in kareler]
        satirlar.append(f"file '{kareler[-1][0]}'")  # FFmpeg concat: son kare tekrar yazilmali
        liste.write_text("\n".join(satirlar) + "\n", encoding="utf-8")

        # 3) Video
        bildir(0.8, "Video oluşturuluyor")
        config.CIKTI_KLASORU.mkdir(exist_ok=True)
        ad = f"{on_ek}_{datetime.now():%Y%m%d_%H%M%S}"
        video = config.CIKTI_KLASORU / f"{ad}.mp4"
        _calistir([
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(liste),
            "-i", str(tum_ses),
            "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", "25",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart",
            str(video),
        ])
        altyazi = config.CIKTI_KLASORU / f"{ad}.srt"
        altyazi.write_text("\n".join(srt), encoding="utf-8")

    bildir(1.0, "Tamamlandı")
    return VideoSonucu(video=video, altyazi=altyazi, sure=toplam_sure, bolum_sayisi=len(sahneler))


def video_olustur(icerik: str, ilerleme=None) -> VideoSonucu:
    """Slayt modu. icerik: LLM'den gelen SSML. ilerleme: fn(oran 0-1, mesaj)"""
    bolumler = bolumlere_ayir(icerik)
    if not bolumler:
        raise VideoHatasi("Seslendirilecek metin bulunamadi.")
    belge_basligi = _baslik(bolumler[0])
    sahneler = [
        Sahne(zemin=slayt_ciz(b, i, len(bolumler), belge_basligi), bolumler=[b], etiket=f"Slayt {i}")
        for i, b in enumerate(bolumler, 1)
    ]
    return _uret(sahneler, ilerleme, "docvoice")


def pdf_videosu_olustur(pdf: bytes, sayfa_ssml: list[str], ilerleme=None) -> VideoSonucu:
    """PDF sayfa modu. sayfa_ssml[i]: i. sayfanin seslendirme metni (bos olabilir)."""
    from services.pdf_pages import sayfa_gorseli

    toplam = len(sayfa_ssml)
    sahneler = []
    for i, ssml in enumerate(sayfa_ssml):
        if ilerleme:
            ilerleme(0.02, f"Sayfa görselleri hazırlanıyor: {i + 1} / {toplam}")
        zemin = sayfa_zemini(sayfa_gorseli(pdf, i), i + 1, toplam)
        try:
            bolumler = bolumlere_ayir(ssml) if ssml.strip() else []
        except ValueError as e:
            raise VideoHatasi(f"Sayfa {i + 1}: {e}") from e
        sahneler.append(Sahne(zemin=zemin, bolumler=bolumler, etiket=f"Sayfa {i + 1}"))
    if not any(s.bolumler for s in sahneler):
        raise VideoHatasi("Hiçbir sayfada seslendirilecek metin yok.")
    return _uret(sahneler, ilerleme, "docvoice_pdf")
