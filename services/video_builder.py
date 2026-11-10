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

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config
from services.ssml_tools import Bolum, bolumlere_ayir
from services.tts_client import TTSHatasi, seslendir

GENISLIK, YUKSEKLIK = 1920, 1080
KENAR = 140
SAG_BOSLUK = 0   # karakter acikken icerigin sagda bos biraktigi alan (piksel); _karakter_alani() ayarlar


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


def _logo_yukle(azami=(260, 70)):
    if not config.VIDEO_LOGO:
        return None
    try:
        logo = Image.open(config.VIDEO_LOGO).convert("RGBA")
    except Exception:
        return None
    # Etrafindaki seffaf bosluklari kirp, boylece logo verilen alana tam oturur
    kutu = logo.getbbox()
    if kutu:
        logo = logo.crop(kutu)
    logo.thumbnail(azami, Image.LANCZOS)
    return logo


def _logo_yerlestir(img: Image.Image, x: int, y: int, azami, zemin: bool) -> int:
    """Logoyu (x, y) konumuna koyar; zemin=True ise arkasina beyaz kutu cizer.
    Logodan sonraki x konumunu dondurur."""
    logo = _logo_yukle(azami)
    if logo is None:
        return x
    if zemin:
        bosluk = 14
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([x, y, x + logo.width + 2 * bosluk, y + logo.height + 2 * bosluk],
                            radius=10, fill=(255, 255, 255))
        img.paste(logo, (x + bosluk, y + bosluk), logo)
        return x + logo.width + 2 * bosluk
    img.paste(logo, (x, y), logo)
    return x + logo.width


def _logo_zemini_gerekli() -> bool:
    ayar = config.VIDEO_LOGO_ZEMIN
    if ayar in ("1", "true", "evet", "yes"):
        return True
    if ayar in ("0", "false", "hayir", "hayır", "no"):
        return False
    # otomatik: logonun gorunen piksellerinin ortalama parlakligi arka plana yakinsa kutu ciz
    logo = _logo_yukle((200, 200))
    if logo is None:
        return False
    gri = logo.convert("LA")
    pikseller = [l for l, a in gri.getdata() if a > 128]
    if not pikseller:
        return False
    return sum(pikseller) / len(pikseller) < 110


def _logo_ekle(img: Image.Image) -> int:
    """Slayt modu: logo varsa sol uste koyar, logodan sonraki x konumunu dondurur."""
    if not config.VIDEO_LOGO:
        return KENAR
    zemin = _logo_zemini_gerekli()
    yukseklik = 70 if not zemin else 52
    logo = _logo_yukle((260, yukseklik))
    if logo is None:
        return KENAR
    y = 95 - (logo.height + (28 if zemin else 0)) // 2   # baslik satiriyla ayni hizada ortala
    return _logo_yerlestir(img, KENAR, y, (260, yukseklik), zemin) + 30


def slayt_ciz(bolum: Bolum, sira: int, toplam: int, belge_basligi: str) -> Image.Image:
    vurgu = _renk(config.VIDEO_ACCENT)
    img = _arka_plan()
    d = ImageDraw.Draw(img)

    # Ust bilgi: logo + belge basligi + sayac
    x = _logo_ekle(img)
    kucuk = _font(True, 26)
    d.text((x, 80), _tr_buyuk(belge_basligi)[:70], font=kucuk, fill=vurgu)
    if config.VIDEO_SAYFA_NO:
        sayac = f"{sira:02d} / {toplam:02d}"
        d.text((GENISLIK - KENAR - kucuk.getlength(sayac), 80), sayac, font=kucuk, fill=(200, 210, 225))
    d.line([(KENAR, 135), (GENISLIK - KENAR, 135)], fill=(70, 90, 120), width=2)

    # Arka planda buyuk, soluk bolum numarasi
    filigran = _font(True, 420)
    d.text((GENISLIK - KENAR - SAG_BOSLUK - filigran.getlength(f"{sira:02d}"), 150), f"{sira:02d}",
           font=filigran, fill=tuple(min(255, c + 7) for c in _renk(config.VIDEO_BG2)))

    # Baslik
    kapak = sira == 1
    font = _font(True, 92 if kapak else 72)
    satirlar = _sar(_baslik(bolum), font, GENISLIK - 2 * KENAR - 60 - SAG_BOSLUK, 3 if kapak else 4)
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

    kutulu = config.VIDEO_ALTYAZI_STIL == "kutu"
    font = _font(not kutulu, 46 if not kutulu else 42)
    alan = GENISLIK - SAG_BOSLUK          # altyazi karakterin solundaki alanda ortalanir
    satirlar = _sar(metin, font, min(1500, alan - 140), 2) if metin.strip() else []
    satir_y = 58
    if satirlar:
        kutu_y = len(satirlar) * satir_y + 44
        genis = max(font.getlength(s) for s in satirlar) + 80
        x0 = (alan - genis) / 2
        y0 = YUKSEKLIK - 70 - kutu_y
        if kutulu:
            d.rounded_rectangle([x0, y0, x0 + genis, y0 + kutu_y], radius=18, fill=(0, 0, 0, 215))
        else:
            # Kutusuz: yazinin arkasinda yumusak, dar bir golge (zeminde siyah bant olusmaz)
            golge = Image.new("RGBA", img.size, (0, 0, 0, 0))
            dg = ImageDraw.Draw(golge)
            for i, s in enumerate(satirlar):
                dg.text(((alan - font.getlength(s)) / 2 + 2, y0 + 25 + i * satir_y), s,
                        font=font, fill=(0, 0, 0, 170))
            katman.alpha_composite(golge.filter(ImageFilter.GaussianBlur(4)))
        for i, s in enumerate(satirlar):
            d.text(((alan - font.getlength(s)) / 2, y0 + 22 + i * satir_y), s, font=font,
                   fill=(255, 255, 255), stroke_width=0 if kutulu else 2, stroke_fill=(0, 0, 0))

    # En altta ilerleme cubugu (sadece dolu kisim; zeminde bant birakmaz)
    if config.VIDEO_ILERLEME:
        d.rectangle([0, YUKSEKLIK - 6, int(GENISLIK * ilerleme), YUKSEKLIK],
                    fill=_renk(config.VIDEO_ACCENT) + (255,))
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


def _kenar_rengi(img: Image.Image) -> tuple:
    """Sayfanin kenar rengini (genelde beyaz) bulur; bos alanlar bu renkle doldurulur."""
    k = img.convert("RGB").resize((64, 64))
    pikseller = [k.getpixel((x, y)) for x in range(64) for y in (0, 63)] + \
                [k.getpixel((x, y)) for y in range(64) for x in (0, 63)]
    return max(set(pikseller), key=pikseller.count)


def _kenarlari_kirp(sayfa: Image.Image, renk: tuple) -> Image.Image:
    """Sayfanin etrafindaki bos (kenar rengindeki) alani kirpar, icerigin cevresinde az pay birakir."""
    from PIL import ImageChops
    kucuk = sayfa.convert("RGB")
    olcek = 4 if min(kucuk.size) > 800 else 1
    kucuk = kucuk.resize((kucuk.width // olcek, kucuk.height // olcek))
    fark = ImageChops.difference(kucuk, Image.new("RGB", kucuk.size, renk)).convert("L")
    kutu = fark.point(lambda v: 255 if v > 18 else 0).getbbox()
    if not kutu:
        return sayfa
    x0, y0, x1, y1 = (v * olcek for v in kutu)
    pay = int(max(x1 - x0, y1 - y0) * 0.04)
    x0, y0 = max(0, x0 - pay), max(0, y0 - pay)
    x1, y1 = min(sayfa.width, x1 + pay), min(sayfa.height, y1 + pay)
    if (x1 - x0) * (y1 - y0) > 0.92 * sayfa.width * sayfa.height:
        return sayfa      # zaten dolu sayfa
    return sayfa.crop((x0, y0, x1, y1))


def sayfa_zemini(sayfa: Image.Image, sira: int, toplam: int, altyazi_alani: bool = True) -> Image.Image:
    """PDF sayfasini ekrana olabildigince buyuk yerlestirir. PDF'ler kendi logosu ve tasarimiyla
    geldigi icin ek arka plan veya logo eklenmez; bos kalan alan sayfanin kendi kenar rengiyle dolar.

    VIDEO_PDF_TAM_EKRAN (varsayilan acik): sayfanin bos kenarlari kirpilir ve icerik tum ekrani
    kullanir; altyazi sayfanin uzerine yazilir. Kapaliysa sayfa tam haliyle, altyazi aciksa
    altyazi bandinin ustunde gosterilir."""
    renk = _kenar_rengi(sayfa)
    zemin = Image.new("RGB", (GENISLIK, YUKSEKLIK), renk)
    if config.VIDEO_PDF_TAM_EKRAN:
        sayfa = _kenarlari_kirp(sayfa, renk)
        alan_h = YUKSEKLIK
    else:
        alan_h = SAYFA_ALANI_ALT if altyazi_alani else YUKSEKLIK
    alan_w = GENISLIK - SAG_BOSLUK
    oran = min(alan_w / sayfa.width, alan_h / sayfa.height)   # en-boy oranini koruyarak sigdir
    on = sayfa.resize((round(sayfa.width * oran), round(sayfa.height * oran)), Image.LANCZOS)
    zemin.paste(on, ((alan_w - on.width) // 2, (alan_h - on.height) // 2))

    if config.VIDEO_SAYFA_NO:
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
    ciz: object = None       # varsa her altyazi parcasi icin zemini yeniden cizer (vurgu icin)


def _sessiz_wav(yol: Path, sure: float) -> float:
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * sure))
    return sure


def _uret(sahneler: list[Sahne], ilerleme, on_ek: str, altyazi: bool = True,
          karakter=False) -> VideoSonucu:
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
        sahne_baslari, cumle_baslari, onceki_sahne = [], [], None   # karakterin jestleri icin
        for si, b, sure in plan:
            sahne = sahneler[si]
            if si != onceki_sahne:
                sahne_baslari.append(zaman)
                onceki_sahne = si
            zemin = sahne.zemin
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
                cumle_baslari.append(zaman)
                k += 1
                ad = f"kare_{k:05d}.png"
                if sahne.ciz:
                    zemin = sahne.ciz(p)   # anlatilan kelimeye gore vurgulu slayt
                # Altyazi kapaliysa ekrana yazilmaz; SRT dosyasi yine de uretilir
                altyazi_ekle(zemin, p if altyazi else "", zaman / toplam_sure).save(tmp / ad)
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
        cikis_secenekleri = [
            "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart",
            str(video),
        ]
        tip = karakter_tipi(karakter)
        if tip in ("sunucu", "maya"):
            bildir(0.8, "Karakter canlandırılıyor")
            _figurlu_video(ffmpeg, liste, tum_ses, sahne_baslari, cumle_baslari, cikis_secenekleri,
                           _figur_modulu(tip))
            komut = None
        elif tip == "ozel":
            bildir(0.8, "Karakter canlandırılıyor")
            karakter_listesi = _karakter_katmani(tmp, tum_ses)
            x, y = _karakter_konumu()
            komut = [
                ffmpeg, "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(liste),
                "-f", "concat", "-safe", "0", "-i", str(karakter_listesi),
                "-i", str(tum_ses),
                "-filter_complex",
                f"[0:v]fps=25,format=rgba[z];[1:v]fps=25,format=rgba[k];"
                f"[z][k]overlay={x}:{y}:eof_action=pass,format=yuv420p[v]",
                "-map", "[v]", "-map", "2:a",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "25",
            ]
        else:
            komut = [
                ffmpeg, "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(liste),
                "-i", str(tum_ses),
                "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p", "-r", "25",
            ]
        if komut:
            _calistir(komut + cikis_secenekleri)
        altyazi = config.CIKTI_KLASORU / f"{ad}.srt"
        altyazi.write_text("\n".join(srt), encoding="utf-8")

    bildir(1.0, "Tamamlandı")
    return VideoSonucu(video=video, altyazi=altyazi, sure=toplam_sure, bolum_sayisi=len(sahneler))


# ------------------------------------------------------------ karakter
KARAKTERLER = {"sunucu": "Sunucu (kadın)", "maya": "Maya (maskot)", "ozel": "Kendi görselim"}


def karakter_tipi(karakter) -> str | None:
    """karakter: False/None (yok), True (.env'deki VIDEO_KARAKTER_TIPI) veya 'sunucu' / 'maya' / 'ozel'."""
    if not karakter:
        return None
    tip = config.VIDEO_KARAKTER_TIPI if karakter is True else str(karakter)
    if tip == "ozel" and not _ozel_karakter():
        tip = "sunucu"      # kendi gorsel seti yoksa varsayilan sunucu
    return tip if tip in KARAKTERLER else "sunucu"


def kullanilabilir_karakterler() -> dict[str, str]:
    return {k: v for k, v in KARAKTERLER.items() if k != "ozel" or _ozel_karakter()}


def _figur_modulu(tip: str):
    if tip == "maya":
        from services import maya
        return maya
    from services import figur
    return figur


def _ozel_karakter() -> bool:
    """KARAKTER_KLASORU'nda kendi gorsel setiniz varsa onu kullan (agiz animasyonu)."""
    from services import karakter
    k = config.KARAKTER_KLASORU
    return bool(k) and all((Path(k) / f"{a}.png").exists() for a in karakter.AGIZ)


def _figurlu_video(ffmpeg, liste, tum_ses, sahne_baslari, cumle_baslari, cikis_secenekleri, figur):
    """Animasyonlu karakter (sunucu veya Maya): kareler ham RGBA olarak FFmpeg'e akitilir ve bindirilir."""
    import subprocess
    import tempfile as _tf

    from services import karakter

    siddet = karakter.ses_siddeti(tum_ses)
    halleri = karakter.agiz_halleri(tum_ses, siddet)
    x, y = figur.konum()
    komut = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(liste),
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "{}x{}".format(*figur.boyut()), "-r", str(figur.FPS),
        "-i", "pipe:0",
        "-i", str(tum_ses),
        "-filter_complex",
        f"[0:v]fps=25,format=rgba[z];[1:v]format=rgba[k];"
        f"[z][k]overlay={x}:{y}:eof_action=pass,format=yuv420p[v]",
        "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "25",
    ] + cikis_secenekleri
    with _tf.TemporaryFile() as hata:
        islem = subprocess.Popen(komut, stdin=subprocess.PIPE, stderr=hata)
        try:
            for durum in figur.animasyon(halleri, siddet, sahne_baslari, cumle_baslari):
                islem.stdin.write(figur.kare_ekran(durum).tobytes())
        except BrokenPipeError:
            pass
        finally:
            try:
                islem.stdin.close()
            except BrokenPipeError:
                pass
        islem.wait()
        if islem.returncode != 0:
            hata.seek(0)
            raise VideoHatasi(f"FFmpeg hatasi:\n{hata.read().decode('utf-8', 'replace')[-1500:]}")


def _karakter_konumu() -> tuple[int, int]:
    from services import karakter
    return karakter.konum()


def _karakter_katmani(tmp: Path, tum_ses: Path) -> Path:
    """Sesten kare kare agiz hallerini cikarir, FFmpeg concat listesi olarak yazar."""
    from services import karakter

    spritelar = karakter.sprite_seti()
    for ad, img in spritelar.items():
        img.save(tmp / f"karakter_{ad}.png")
    halleri = karakter.agiz_halleri(tum_ses)
    # Ardisik ayni kareleri birlestir (daha kisa liste, ayni sonuc)
    satirlar, onceki, sayi = [], None, 0
    for h in halleri + [None]:
        if h == onceki:
            sayi += 1
            continue
        if onceki is not None:
            satirlar.append(f"file 'karakter_{onceki}.png'\nduration {sayi / karakter.FPS:.3f}")
        onceki, sayi = h, 1
    satirlar.append(f"file 'karakter_{halleri[-1]}.png'")
    liste = tmp / "karakter.txt"
    liste.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return liste


class _karakter_alani:
    """with blogu icinde cizilen her sey karakter icin sagda yer birakir."""

    def __init__(self, acik: bool):
        self.acik = acik

    def __enter__(self):
        global SAG_BOSLUK
        tip = karakter_tipi(self.acik)
        if tip == "ozel":
            from services import karakter
            SAG_BOSLUK = karakter.GEN + 40
        elif tip:
            SAG_BOSLUK = _figur_modulu(tip).sag_alan()

    def __exit__(self, *a):
        global SAG_BOSLUK
        SAG_BOSLUK = 0


def video_olustur(icerik: str, ilerleme=None, altyazi: bool = True,
                  karakter=False) -> VideoSonucu:
    """Slayt modu. karakter: False, True veya 'sunucu' / 'maya' / 'ozel'. icerik: LLM'den gelen SSML. ilerleme: fn(oran 0-1, mesaj)"""
    bolumler = bolumlere_ayir(icerik)
    if not bolumler:
        raise VideoHatasi("Seslendirilecek metin bulunamadi.")
    belge_basligi = _baslik(bolumler[0])
    with _karakter_alani(karakter):
        sahneler = [
            Sahne(zemin=slayt_ciz(b, i, len(bolumler), belge_basligi), bolumler=[b], etiket=f"Slayt {i}")
            for i, b in enumerate(bolumler, 1)
        ]
        return _uret(sahneler, ilerleme, "docvoice", altyazi, karakter)


def pdf_videosu_olustur(pdf: bytes, sayfa_ssml: list[str], ilerleme=None,
                        altyazi: bool = True, sunum: bool = False,
                        karakter=False) -> VideoSonucu:
    with _karakter_alani(karakter):
        return _pdf_videosu(pdf, sayfa_ssml, ilerleme, altyazi, sunum, karakter)


def _pdf_videosu(pdf, sayfa_ssml, ilerleme, altyazi, sunum, karakter) -> VideoSonucu:
    """PDF sayfa modu. sayfa_ssml[i]: i. sayfanin seslendirme metni (bos olabilir).
    sunum=True: gosterge karti bulunan sayfalar modern slayt olarak yeniden cizilir."""
    from services.pdf_pages import sayfa_gorseli
    if sunum:
        from services.pdf_kartlar import sayfa_duzeni
        from services.sunum_cizim import SunumCizici

    toplam = len(sayfa_ssml)
    sahneler = []
    for i, ssml in enumerate(sayfa_ssml):
        if ilerleme:
            ilerleme(0.02, f"Sayfa görselleri hazırlanıyor: {i + 1} / {toplam}")
        ciz = None
        duzen = sayfa_duzeni(pdf, i) if sunum else None
        if duzen:
            ciz = SunumCizici(duzen, i + 1, toplam, altyazi_alani=altyazi)
            zemin = ciz("")
        else:
            zemin = sayfa_zemini(sayfa_gorseli(pdf, i), i + 1, toplam, altyazi_alani=altyazi)
        try:
            bolumler = bolumlere_ayir(ssml) if ssml.strip() else []
        except ValueError as e:
            raise VideoHatasi(f"Sayfa {i + 1}: {e}") from e
        sahneler.append(Sahne(zemin=zemin, bolumler=bolumler, etiket=f"Sayfa {i + 1}", ciz=ciz))
    if not any(s.bolumler for s in sahneler):
        raise VideoHatasi("Hiçbir sayfada seslendirilecek metin yok.")
    return _uret(sahneler, ilerleme, "docvoice_pdf", altyazi, karakter)
