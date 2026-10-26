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
from services.tts_client import seslendir

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
    satirlar = _sar(metin, font, 1500, 2)
    satir_y = 58
    kutu_y = len(satirlar) * satir_y + 44
    genis = max(font.getlength(s) for s in satirlar) + 80
    x0 = (GENISLIK - genis) / 2
    y0 = YUKSEKLIK - 70 - kutu_y
    d.rounded_rectangle([x0, y0, x0 + genis, y0 + kutu_y], radius=18, fill=(0, 0, 0, 170))
    for i, s in enumerate(satirlar):
        d.text(((GENISLIK - font.getlength(s)) / 2, y0 + 22 + i * satir_y), s, font=font, fill=(255, 255, 255))

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


# ---------------------------------------------------------------- ana akis
def video_olustur(icerik: str, ilerleme=None) -> VideoSonucu:
    """icerik: LLM'den gelen SSML. ilerleme: fn(oran 0-1, mesaj)"""

    def bildir(oran, mesaj):
        if ilerleme:
            ilerleme(min(oran, 1.0), mesaj)

    bolumler = bolumlere_ayir(icerik)
    if not bolumler:
        raise VideoHatasi("Seslendirilecek metin bulunamadi.")

    ffmpeg = ffmpeg_yolu()
    belge_basligi = _baslik(bolumler[0])
    toplam = len(bolumler)

    with tempfile.TemporaryDirectory(prefix="docvoice_") as gecici:
        tmp = Path(gecici)

        # 1) Her bolumu seslendir
        wavlar, sureler = [], []
        for i, b in enumerate(bolumler, 1):
            bildir(0.6 * (i - 1) / toplam, f"Seslendiriliyor: bölüm {i} / {toplam}")
            ses, _ = seslendir(f'{b.ssml}<break time="{b.ara_sure}"/>')
            ham = tmp / f"bolum_{i:03d}.ses"
            ham.write_bytes(ses)
            wav = tmp / f"bolum_{i:03d}.wav"
            sureler.append(_wav_yap(ffmpeg, ham, wav))
            wavlar.append(wav)

        tum_ses = tmp / "tum.wav"
        _wav_birlestir(wavlar, tum_ses)
        toplam_sure = sum(sureler)

        # 2) Kareleri ciz, sureleri hesapla
        bildir(0.65, "Slaytlar çiziliyor")
        kareler, srt, zaman, n = [], [], 0.0, 0
        for i, (b, sure) in enumerate(zip(bolumler, sureler), 1):
            slayt = slayt_ciz(b, i, toplam, belge_basligi)
            parcalar = b.cumleler or [b.metin]
            harf = sum(len(p) for p in parcalar) or 1
            for p in parcalar:
                p_sure = sure * len(p) / harf
                n += 1
                ad = f"kare_{n:04d}.png"
                altyazi_ekle(slayt, p, zaman / toplam_sure).save(tmp / ad)
                kareler.append((ad, p_sure))
                srt.append(f"{n}\n{_srt_zaman(zaman)} --> {_srt_zaman(zaman + p_sure)}\n{p}\n")
                zaman += p_sure

        liste = tmp / "liste.txt"
        satirlar = [f"file '{ad}'\nduration {s:.3f}" for ad, s in kareler]
        satirlar.append(f"file '{kareler[-1][0]}'")  # FFmpeg concat: son kare tekrar yazilmali
        liste.write_text("\n".join(satirlar) + "\n", encoding="utf-8")

        # 3) Video
        bildir(0.8, "Video oluşturuluyor")
        config.CIKTI_KLASORU.mkdir(exist_ok=True)
        ad = f"docvoice_{datetime.now():%Y%m%d_%H%M%S}"
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
    return VideoSonucu(video=video, altyazi=altyazi, sure=toplam_sure, bolum_sayisi=toplam)
