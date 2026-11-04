"""Tum vucut, animasyonlu kadin sunucu figuru.

Iskelet tabanli: her karede kol acilari, nefes, salinim, bas egimi, agiz ve goz durumuna gore
cizilir. Parcalar (bas, govde, kollar) ayri katmanlarda onbellege alinir; ayni durum ikinci kez
cizilmez. Kareler ham RGBA olarak FFmpeg'e akitilir.

Koordinatlar 1x olcekte; cizim OLCEK kat buyuk yapilip kucultulur (kenar yumusatma).
"""
import math
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

import config

W, H = 600, 960            # figur tuvali (videodaki boyut)
OLCEK = 2
FPS = 25
CX = 400                   # vucut merkezi (solda gosterme kolu icin yer var)
SAG_ALAN = 290             # icerigin sagda birakacagi bosluk (figurun govdesi bu alanda)

TEN, TEN_G = (243, 204, 175), (226, 178, 146)
SAC, SAC_A = (72, 44, 34), (98, 62, 48)
CEKET, CEKET_A = (54, 66, 86), (70, 84, 106)
PANTOLON, AYAKKABI = (42, 50, 66), (30, 30, 36)
DUDAK = (190, 78, 90)

# Kol duruslari: (ust kol acisi, on kol acisi) derece; 0 = asagi, + = disari, -90 = ice-yatay, 180 = yukari
DURUS = {
    "bosta":    {"sol": (9, 4),     "sag": (9, 4)},
    "goster":   {"sol": (104, 98),  "sag": (12, -18)},     # sol kol (ekranin solu) icerige uzanir
    "anlat":    {"sol": (14, -48),  "sag": (14, -40)},     # on kollar onde, bel hizasinda
    "acik":     {"sol": (26, 108),  "sag": (26, 108)},     # avuclar acik, karsilama
}
EL = {"bosta": "rahat", "goster": "isaret", "anlat": "rahat", "acik": "acik"}


def _r(hex_kod):
    h = hex_kod.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _acik(renk, oran):
    return tuple(int(x + (255 - x) * oran) for x in renk)


# ------------------------------------------------------------------ cizim
class _Kalem:
    """1x koordinatlarla, OLCEK kat buyuk tuvale cizer."""

    def __init__(self, gen, yuk, ox=0, oy=0):
        """ox, oy: bu tuvalin sol ust kosesinin 1x koordinati (kucuk yerel tuvaller icin)."""
        self.ox, self.oy = ox, oy
        self.img = Image.new("RGBA", (int(gen * OLCEK), int(yuk * OLCEK)), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def _p(self, pts):
        return [((x - self.ox) * OLCEK, (y - self.oy) * OLCEK) for x, y in pts]

    def _k(self, x0, y0, x1, y1):
        return [(x0 - self.ox) * OLCEK, (y0 - self.oy) * OLCEK, (x1 - self.ox) * OLCEK, (y1 - self.oy) * OLCEK]

    def elips(self, x0, y0, x1, y1, renk, **k):
        self.d.ellipse(self._k(x0, y0, x1, y1), fill=renk, **k)

    def kutu(self, x0, y0, x1, y1, r, renk):
        self.d.rounded_rectangle(self._k(x0, y0, x1, y1), radius=r * OLCEK, fill=renk)

    def cokgen(self, pts, renk):
        self.d.polygon(self._p(pts), fill=renk)

    def cizgi(self, pts, renk, kalinlik):
        self.d.line(self._p(pts), fill=renk, width=int(kalinlik * OLCEK), joint="curve")

    def kapsul(self, a, b, kalinlik, renk):
        self.cizgi([a, b], renk, kalinlik)
        r = kalinlik / 2
        for x, y in (a, b):
            self.elips(x - r, y - r, x + r, y + r, renk)

    def yay(self, kutu, bas, son, renk, kalinlik):
        self.d.arc(self._k(*kutu), bas, son, fill=renk, width=int(kalinlik * OLCEK))

    def bitir(self) -> Image.Image:
        return self.img.resize((self.img.width // OLCEK, self.img.height // OLCEK), Image.LANCZOS)


def _kirp(img: Image.Image):
    """Seffaf kenarlari kirpar. Doner: (gorsel, (x, y))"""
    kutu = img.getbbox()
    if not kutu:
        return img, (0, 0)
    return img.crop(kutu), (kutu[0], kutu[1])


def _egri(p0, p1, p2, n=14):
    """Ikinci derece Bezier egrisi uzerinde noktalar (yumusak sac hatlari icin)."""
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / n for i in range(n + 1))]


def _yumusak_golge(k: "_Kalem", cizimler, maske_elips, bulaniklik=7):
    """cizimler: [(x0, y0, x1, y1, rgba)] elipsleri bulaniklastirip maske elipsinin icinde birakir."""
    from PIL import ImageChops
    g = _Kalem(k.img.width // OLCEK, k.img.height // OLCEK, k.ox, k.oy)
    for x0, y0, x1, y1, renk in cizimler:
        g.elips(x0, y0, x1, y1, renk)
    g.img = g.img.filter(ImageFilter.GaussianBlur(bulaniklik * OLCEK))
    maske = Image.new("L", k.img.size, 0)
    ImageDraw.Draw(maske).ellipse(k._k(*maske_elips), fill=255)
    g.img.putalpha(ImageChops.multiply(g.img.split()[3], maske))
    k.img.alpha_composite(g.img)
    k.d = ImageDraw.Draw(k.img)


# Bas katmani yerel tuvali: bas merkezi (BX, BY), boyun donme noktasi (BX, PY)
BW, BH, BX, BY, PY = 300, 330, 150, 150, 262


@lru_cache(maxsize=128)
def _bas(agiz: int, goz_kapali: bool, kas: int, egim: int):
    """On sac + yuz. kas: 0 normal, 1 kalkik. egim: derece (donme)."""
    k = _Kalem(BW, BH)
    vurgu = _r(config.VIDEO_ACCENT)
    c, y = BX, BY
    # Kulaklar ve kupeler
    k.elips(c - 70, y - 4, c - 50, y + 34, TEN_G)
    k.elips(c + 50, y - 4, c + 70, y + 34, TEN_G)
    k.elips(c - 66, y + 34, c - 56, y + 44, vurgu)
    k.elips(c + 56, y + 34, c + 66, y + 44, vurgu)
    # Yuz ve hafif hacim golgesi (perce alti, yanaklar, cene)
    yuz = (c - 58, y - 72, c + 58, y + 78)
    k.elips(*yuz, TEN)
    _yumusak_golge(k, [(c - 60, y - 84, c + 60, y - 40, TEN_G + (110,)),
                       (c - 80, y - 10, c - 46, y + 66, TEN_G + (70,)),
                       (c + 46, y - 10, c + 80, y + 66, TEN_G + (70,))], yuz, bulaniklik=8)
    # On sac: yuvarlak tepe + yana taranmis yumusak perce + yuz kenarinda tutam
    k.d.chord(k._k(c - 66, y - 102, c + 66, y - 8), 180, 360, fill=SAC)
    # Yana taranmis perce: soldan saga dogru alnin ustunden kivrilarak sag sakaga iner
    perce = (_egri((c - 64, y - 52), (c - 30, y - 70), (c + 6, y - 66))
             + _egri((c + 6, y - 66), (c + 50, y - 58), (c + 64, y - 4))
             + _egri((c + 64, y - 4), (c + 40, y - 30), (c + 10, y - 40))
             + _egri((c + 10, y - 40), (c - 30, y - 50), (c - 64, y - 30)))
    k.cokgen(perce, SAC)
    k.cokgen(_egri((c - 62, y - 40), (c - 70, y + 10), (c - 54, y + 52))
             + _egri((c - 54, y + 52), (c - 58, y + 6), (c - 50, y - 30)), SAC)
    # Sac parlamasi
    k.yay((c - 46, y - 92, c + 30, y - 40), 200, 290, SAC_A, 5)
    k.yay((c - 10, y - 84, c + 56, y - 30), 250, 320, SAC_A, 3)
    # Kaslar (ince, kavisli)
    ky = y - 22 - (6 if kas else 0)
    k.yay((c - 44, ky, c - 12, ky + 12), 205, 335, SAC, 3)
    k.yay((c + 12, ky, c + 44, ky + 12), 205, 335, SAC, 3)
    # Gozler (kirpikli)
    for gx in (c - 27, c + 27):
        if goz_kapali:
            k.yay((gx - 13, y - 2, gx + 13, y + 14), 20, 160, (70, 45, 40), 3.5)
        else:
            k.elips(gx - 12, y - 10, gx + 12, y + 14, (255, 255, 255))
            k.elips(gx - 8, y - 6, gx + 8, y + 12, (78, 54, 44))
            k.elips(gx - 3, y - 3, gx + 2, y + 2, (255, 255, 255))
            k.yay((gx - 13, y - 12, gx + 13, y + 10), 200, 340, (50, 32, 28), 3.5)
            dis = gx + (13 if gx > c else -13)
            k.cizgi([(dis, y - 4), (dis + (6 if gx > c else -6), y - 10)], (50, 32, 28), 2.5)
    # Burun, yanaklar
    k.yay((c - 8, y + 12, c + 8, y + 32), 30, 150, TEN_G, 3)
    allik = _Kalem(BW, BH)
    allik.elips(c - 52, y + 26, c - 28, y + 42, (240, 140, 140, 80))
    allik.elips(c + 28, y + 26, c + 52, y + 42, (240, 140, 140, 80))
    k.img.alpha_composite(allik.img)
    k.d = ImageDraw.Draw(k.img)
    # Agiz
    if agiz == 0:
        k.yay((c - 20, y + 32, c + 20, y + 56), 20, 160, DUDAK, 4.5)
        k.yay((c - 10, y + 50, c + 10, y + 60), 20, 160, _acik(DUDAK, 0.35), 3)
    elif agiz == 1:
        k.elips(c - 15, y + 44, c + 15, y + 62, (120, 40, 46))
        k.elips(c - 9, y + 53, c + 9, y + 62, (225, 115, 115))
        k.yay((c - 16, y + 41, c + 16, y + 64), 200, 340, DUDAK, 3)
    else:
        k.elips(c - 15, y + 41, c + 15, y + 67, (120, 40, 46))
        k.d.chord(k._k(c - 12, y + 41, c + 12, y + 52), 0, 180, fill=(255, 255, 255))
        k.elips(c - 9, y + 57, c + 9, y + 66, (225, 115, 115))
        k.yay((c - 16, y + 39, c + 16, y + 69), 200, 340, DUDAK, 3)
    img = k.bitir()
    if egim:
        img = img.rotate(-egim, resample=Image.BICUBIC, center=(BX, PY))
    return _kirp(img)


@lru_cache(maxsize=32)
def _arka_sac(egim: int):
    """Basin arkasinda kalan uzun sac (omuzlara kadar)."""
    k = _Kalem(BW, BH)
    c, y = BX, BY
    k.elips(c - 70, y - 104, c + 70, y + 40, SAC)
    k.cokgen(_egri((c - 68, y - 30), (c - 84, y + 80), (c - 80, y + 160))
             + _egri((c - 80, y + 160), (c, y + 190), (c + 80, y + 160))
             + _egri((c + 80, y + 160), (c + 84, y + 80), (c + 68, y - 30)), SAC)
    k.cizgi(_egri((c - 74, y + 20), (c - 82, y + 100), (c - 70, y + 165)), SAC_A, 3)
    k.cizgi(_egri((c + 74, y + 20), (c + 82, y + 100), (c + 70, y + 165)), SAC_A, 3)
    img = k.bitir()
    if egim:
        img = img.rotate(-egim, resample=Image.BICUBIC, center=(BX, PY))
    return _kirp(img)


def _omuzlar(nefes: int):
    oy = 300 - nefes
    return (CX - 82, oy), (CX + 82, oy)


@lru_cache(maxsize=8)
def _govde(nefes: int):
    """Bacaklar, ayakkabilar, govde (ceket + bluz), boyun. nefes: 0-3 (omuzlar yukselir)."""
    k = _Kalem(W, H)
    vurgu = _r(config.VIDEO_ACCENT)
    (sx, sy), (rx, ry) = _omuzlar(nefes)
    # Bacaklar (pantolon) ve ayakkabilar; ust kisim kalcayi doldurur
    k.kutu(CX - 74, 450, CX + 74, 600, 24, PANTOLON)
    # Iki bacak tek parca: ic kontur cizgisi olusmasin, aradaki acilim kasiktan baslar
    k.cokgen([(CX - 72, 560), (CX - 56, 900), (CX - 14, 900), (CX, 650), (CX + 14, 900),
              (CX + 56, 900), (CX + 72, 560)], PANTOLON)
    k.kutu(CX - 70, 888, CX - 6, 916, 12, AYAKKABI)
    k.kutu(CX + 6, 888, CX + 70, 916, 12, AYAKKABI)
    # Boyun (cene altinda golge)
    k.kutu(CX - 15, 236, CX + 15, sy + 20, 8, TEN)
    k.kutu(CX - 15, 236, CX + 15, 262, 8, TEN_G)
    # Bluz (V yaka)
    k.cokgen([(CX - 50, sy - 2), (CX + 50, sy - 2), (CX + 44, 500), (CX - 44, 500)], vurgu)
    k.cokgen([(CX - 22, sy - 4), (CX + 22, sy - 4), (CX, sy + 40)], TEN_G)
    # Ceket: omuzlardan bele, belde hafif darlik, kalcaya kadar
    k.cokgen([(sx - 6, sy + 10), (sx + 18, sy - 6), (CX - 34, sy - 6), (CX - 14, sy + 120), (CX - 26, 470),
              (CX - 62, 470), (CX - 74, 580), (CX - 96, 580), (CX - 88, 470), (sx - 10, sy + 60)], CEKET)
    k.cokgen([(rx + 6, sy + 10), (rx - 18, sy - 6), (CX + 34, sy - 6), (CX + 14, sy + 120), (CX + 26, 470),
              (CX + 62, 470), (CX + 74, 580), (CX + 96, 580), (CX + 88, 470), (rx + 10, sy + 60)], CEKET)
    k.elips(sx - 22, sy - 8, sx + 26, sy + 40, CEKET)
    k.elips(rx - 26, sy - 8, rx + 22, sy + 40, CEKET)
    # Hacim: ceketin dis kenarlari biraz daha koyu
    koyu = tuple(int(x * 0.82) for x in CEKET)
    k.cokgen([(sx - 10, sy + 40), (sx + 6, sy + 40), (CX - 70, 470), (CX - 82, 575), (CX - 96, 580),
              (CX - 88, 470)], koyu)
    k.cokgen([(rx + 10, sy + 40), (rx - 6, sy + 40), (CX + 70, 470), (CX + 82, 575), (CX + 96, 580),
              (CX + 88, 470)], koyu)
    # Yakalar
    k.cokgen([(CX - 34, sy - 6), (CX - 14, sy + 120), (CX - 46, sy + 60)], CEKET_A)
    k.cokgen([(CX + 34, sy - 6), (CX + 14, sy + 120), (CX + 46, sy + 60)], CEKET_A)
    # Ceket onunde bel ve dugme
    k.elips(CX - 5, sy + 150, CX + 5, sy + 160, _acik(CEKET, 0.3))
    # Rozet
    k.elips(CX + 48, sy + 70, CX + 62, sy + 84, vurgu)
    return _kirp(k.bitir())


def _kol_noktalari(omuz, a1, a2, yon):
    """yon: -1 ekranin solundaki kol, +1 sagdaki. Doner: (dirsek, bilek)."""
    UST, ON = 132, 118

    def v(aci, boy):
        r = math.radians(aci)
        return yon * math.sin(r) * boy, math.cos(r) * boy
    dx, dy = v(a1, UST)
    dirsek = (omuz[0] + dx, omuz[1] + dy)
    dx, dy = v(a2, ON)
    return dirsek, (dirsek[0] + dx, dirsek[1] + dy)


@lru_cache(maxsize=1024)
def _kol(nefes, taraf, a1, a2, el):
    """Tek kol, sadece kapladigi alan kadar yerel tuvalde. Doner: (gorsel, (x, y)) tuval koordinatinda."""
    omuz = _omuzlar(nefes)[0 if taraf == "sol" else 1]
    yon = -1 if taraf == "sol" else 1
    dirsek, bilek = _kol_noktalari(omuz, a1, a2, yon)
    pay = 70
    xs, ys = [omuz[0], dirsek[0], bilek[0]], [omuz[1], dirsek[1], bilek[1]]
    ox, oy = min(xs) - pay, min(ys) - pay
    k = _Kalem(max(xs) - ox + pay, max(ys) - oy + pay, ox, oy)

    k.kapsul(omuz, dirsek, 40, CEKET)
    k.kapsul(dirsek, bilek, 34, CEKET)
    aci = math.atan2(bilek[1] - dirsek[1], bilek[0] - dirsek[0])
    ux, uy = math.cos(aci), math.sin(aci)
    manset = (bilek[0] - ux * 4, bilek[1] - uy * 4)
    k.kapsul((manset[0] - ux * 6, manset[1] - uy * 6), manset, 30, _acik(CEKET, 0.15))
    merkez = (bilek[0] + ux * 16, bilek[1] + uy * 16)
    if el == "isaret":
        # Acik avuc, parmaklar ileri (gosterme yonunde), basparmak yukarida
        k.elips(merkez[0] - 17, merkez[1] - 15, merkez[0] + 17, merkez[1] + 15, TEN)
        uc = (merkez[0] + ux * 26, merkez[1] + uy * 26)
        k.kapsul(merkez, uc, 24, TEN)
        for kay in (-8, 0, 8):   # parmak ayrimlari
            px, py = merkez[0] + ux * 14 - uy * kay, merkez[1] + uy * 14 + ux * kay
            k.cizgi([(px, py), (px + ux * 14, py + uy * 14)], TEN_G, 1.5)
        k.kapsul((merkez[0] - uy * 10, merkez[1] - 10), (merkez[0] + ux * 8 - uy * 6, merkez[1] - 24), 11, TEN)
    elif el == "acik":
        k.elips(merkez[0] - 16, merkez[1] - 18, merkez[0] + 16, merkez[1] + 16, TEN)
        k.kapsul(merkez, (merkez[0] + yon * 14, merkez[1] - 20), 9, TEN)
    else:
        k.elips(merkez[0] - 15, merkez[1] - 16, merkez[0] + 15, merkez[1] + 18, TEN)
    img, (x, y) = _kirp(k.bitir())
    return img, (int(ox) + x, int(oy) + y)


# ------------------------------------------------------------- kare durumu
@dataclass
class Durum:
    agiz: int = 0
    goz_kapali: bool = False
    kas: int = 0
    egim: int = 0
    nefes: int = 0
    salinim: int = 0
    sol: tuple = (9, 4)
    sag: tuple = (9, 4)
    el_sol: str = "rahat"
    el_sag: str = "rahat"


def oran() -> float:
    """Figurun ekrandaki boyut orani (VIDEO_KARAKTER_BOYUT, varsayilan 0.8)."""
    return max(0.4, min(1.2, float(getattr(config, "VIDEO_KARAKTER_BOYUT", 0.8))))


def boyut() -> tuple[int, int]:
    o = oran()
    return int(W * o) // 2 * 2, int(H * o) // 2 * 2


def sag_alan() -> int:
    """Icerigin sagda birakacagi bosluk (figur boyutuna gore)."""
    return int(SAG_ALAN * oran())


def kare_ekran(durum: "Durum") -> Image.Image:
    """Videoya bindirilecek kare: olceklenmis, siluetin etrafinda yumusak acik hale (koyu zeminde
    secilsin diye; acik zeminde neredeyse gorunmez)."""
    img = kare(durum)
    if boyut() != (W, H):
        img = img.resize(boyut(), Image.BILINEAR)
    alfa = img.split()[3]
    hale = Image.new("RGBA", img.size, (255, 255, 255, 0))
    hale.putalpha(alfa.filter(ImageFilter.GaussianBlur(3)).point(lambda a: min(255, a) * 70 // 255))
    hale.alpha_composite(img)
    return hale


def kare(durum: Durum) -> Image.Image:
    """Tek bir kareyi (W x H, RGBA) birlestirir."""
    tuval = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ox = durum.salinim
    (bx, by) = (CX - BX + ox, 300 - durum.nefes - 22 - PY)   # boyun donme noktasi omuz hizasinin ustunde

    sac, (sx, sy) = _arka_sac(durum.egim)
    tuval.alpha_composite(sac, (bx + sx, by + sy))
    govde, (gx, gy) = _govde(durum.nefes)
    tuval.alpha_composite(govde, (gx + ox, gy))
    bas, (hx, hy) = _bas(durum.agiz, durum.goz_kapali, durum.kas, durum.egim)
    tuval.alpha_composite(bas, (bx + hx, by + hy))
    for taraf, (a1, a2), el in (("sol", durum.sol, durum.el_sol), ("sag", durum.sag, durum.el_sag)):
        kol, (kx, ky) = _kol(durum.nefes, taraf, a1, a2, el)
        tuval.alpha_composite(kol, (kx + ox, ky))
    return tuval


def golgeli(img: Image.Image) -> Image.Image:
    """Ince acik kontur + hafif golge: her zeminde secilsin (onizleme ve sabit gorseller icin)."""
    alfa = img.split()[3]
    kontur = Image.new("RGBA", img.size, (255, 255, 255, 0))
    kontur.putalpha(alfa.filter(ImageFilter.MaxFilter(5)).point(lambda a: 100 if a > 40 else 0))
    sonuc = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sonuc.alpha_composite(kontur)
    sonuc.alpha_composite(img)
    return sonuc


# ------------------------------------------------------------- animasyon
def konum() -> tuple[int, int]:
    """Figur tuvalinin videodaki sol ust kosesi: govde sag altta, ayaklar alt kenara yakin."""
    from services.video_builder import GENISLIK, YUKSEKLIK
    o = oran()
    return int(GENISLIK - 150 * o - CX * o), int(YUKSEKLIK - 24 - 916 * o)


def _yumusak(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _jest_plani(sure: float, sahne_baslari: list[float], cumle_baslari: list[float],
                konusuyor) -> list[tuple]:
    """[(baslangic, bitis, durus)]
    - sahne (sayfa/slayt) basinda: sola, icerige dogru gosterme
    - cumle baslarinda: sirayla anlatma / gosterme / acik el
    - uzun konusmalarda 5 sn'den fazla jestsiz kalinmaz
    """
    plan = []

    def bos_mu(b0, b1):
        return all(b1 + 0.6 < p0 or b0 > p1 + 1.0 for p0, p1, _ in plan)

    for t in sahne_baslari:
        b0 = max(0.3, t + 0.2)
        if b0 < sure - 1.5:
            plan.append((b0, min(sure, b0 + 2.8), "goster"))

    sira = ["anlat", "goster", "acik", "anlat", "acik"]
    n = 0
    for t in cumle_baslari:
        b0, b1 = t + 0.15, min(sure, t + 2.6)
        if b1 - b0 >= 1.5 and konusuyor(b0 + 0.6) and bos_mu(b0, b1):
            plan.append((b0, b1, sira[n % len(sira)]))
            n += 1

    t = 0.5
    while t < sure - 2:
        yakin = any(p0 - 2.6 <= t <= p1 + 2.5 for p0, p1, _ in plan)
        if not yakin and konusuyor(t) and bos_mu(t, t + 2.4):
            plan.append((t, t + 2.4, sira[n % len(sira)]))
            n += 1
            t += 3
        t += 0.5
    return sorted(plan)


def animasyon(halleri: list[str], siddet: list[float], sahne_baslari: list[float],
              cumle_baslari: list[float]):
    """Her kare icin Durum ureten jenerator. halleri: karakter.agiz_halleri ciktisi."""
    kare_sayisi = len(halleri)
    sure = kare_sayisi / FPS

    def konusuyor(t):
        # Kelime aralarindaki kisa sessizlikler sayilmasin: +-0,6 sn pencere
        i = int(t * FPS)
        pencere = siddet[max(0, i - 15):i + 15]
        return bool(pencere) and sum(1 for x in pencere if x > 0.15) > len(pencere) * 0.3

    plan = _jest_plani(sure, sahne_baslari, cumle_baslari, konusuyor)
    bosta = DURUS["bosta"]
    enerji = 0.0
    for i in range(kare_sayisi):
        t = i / FPS
        ad = halleri[i]
        enerji = enerji * 0.8 + (siddet[i] if i < len(siddet) else 0) * 0.2

        # Aktif jest ve agirligi (0-1, yumusak giris/cikis)
        jest, w = None, 0.0
        for p0, p1, d in plan:
            if p0 - 0.05 <= t <= p1 + 0.45:
                w = min(_yumusak((t - p0) / 0.45), 1 - _yumusak((t - p1) / 0.45))
                jest = d
                break
        hedef = DURUS[jest] if jest else bosta

        def kol(taraf, faz):
            a1 = bosta[taraf][0] + (hedef[taraf][0] - bosta[taraf][0]) * w
            a2 = bosta[taraf][1] + (hedef[taraf][1] - bosta[taraf][1]) * w
            # Canlilik: bostayken hafif sallanma, anlatirken on kol ritmik hareket
            a1 += 2.0 * math.sin(2 * math.pi * t / 4.1 + faz)
            if jest == "anlat":
                a2 += 12 * w * math.sin(2 * math.pi * 1.4 * t + faz)
            elif jest in ("goster", "acik"):
                a2 += 4 * w * math.sin(2 * math.pi * 0.9 * t + faz)
            # Konusurken jest yoksa eller vurgularla hafifce hareket eder
            a2 -= (1 - w) * 26 * enerji * (0.6 + 0.4 * math.sin(2 * math.pi * 0.7 * t + faz))
            return (int(round(a1 / 3) * 3), int(round(a2 / 4) * 4))   # onbellek icin yuvarla

        el = EL[jest] if (jest and w > 0.5) else "rahat"
        egim = 2.2 * math.sin(2 * math.pi * t / 5.3) + 2.5 * enerji * math.sin(2 * math.pi * 2.1 * t)
        if jest == "goster":
            egim -= 3 * w        # gosterdigi yone (sola) dogru hafif bas egimi
        yield Durum(
            agiz={"kapali": 0, "kirpik": 0, "yarim": 1, "acik": 2}[ad],
            goz_kapali=ad == "kirpik",
            kas=1 if (jest == "goster" and w > 0.5) or enerji > 0.85 else 0,
            egim=max(-5, min(5, int(round(egim)))),
            nefes=int(round((1 + math.sin(2 * math.pi * t / 4.0)) * 1.5)),
            salinim=int(round(3 * math.sin(2 * math.pi * t / 6.7))),
            sol=kol("sol", 0.0),
            sag=kol("sag", 1.3),
            el_sol=el,
            el_sag=el if jest != "goster" else "rahat",
        )
