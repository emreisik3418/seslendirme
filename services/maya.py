"""Maya: oturan, kivircik tuylu maskot kopek (turuncu kapitone yelek, siyah tasma).

figur.py ile ayni arayuz: W, H, FPS, animasyon(), kare(), kare_ekran(), boyut(), sag_alan(), konum()
Animasyon: konusurken agiz acilir ve dil gorunur, kuyruk sallanir, kafa yatirma, kulak sallanmasi,
yeni sayfada sol on patiyle icerige dogru gosterme, mutlu ziplama, goz kirpma.
"""
import math
import random
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageFilter

import config
from services.figur import _egri, _kirp, _Kalem, _yumusak, OLCEK

W, H = 520, 640
FPS = 25
CX = 300
SAG_ALAN = 300

TUY = (224, 186, 142)
TUY_A = (240, 212, 176)
TUY_K = (196, 152, 108)
TUY_KK = (170, 126, 86)
YELEK = (255, 112, 24)
YELEK_K = (222, 84, 8)
TASMA = (38, 38, 46)
BURUN = (34, 26, 26)
DIL = (236, 112, 132)


def _kivircik(k: _Kalem, cx, cy, rx, ry, tohum, adet=70, r=(7, 12), tonlar=(TUY_A, TUY, TUY_K)):
    """Kivircik tuy dokusu: elips icine birbirine yakin tonlarda kucuk yumaklar ve ince kivrim yaylari
    (sabit tohum: her karede ayni doku)."""
    rnd = random.Random(tohum)
    acik, orta, koyu = tonlar
    yakin = [tuple(int(a * 0.55 + b * 0.45) for a, b in zip(acik, orta)), orta,
             tuple(int(a * 0.6 + b * 0.4) for a, b in zip(orta, koyu))]
    for _ in range(adet):
        a = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(0.3, 1.0) ** 0.6
        x, y = cx + math.cos(a) * rx * d, cy + math.sin(a) * ry * d
        yr = rnd.uniform(*r)
        k.elips(x - yr, y - yr, x + yr, y + yr, rnd.choice(yakin))
        if rnd.random() < 0.6:   # kivrim: yumagin alt kenarinda ince koyu yay
            k.yay((x - yr * 0.8, y - yr * 0.8, x + yr * 0.8, y + yr * 0.8),
                  rnd.choice((20, 200)), rnd.choice((150, 330)), koyu, 1.6)


def _tuylu_elips(k: _Kalem, cx, cy, rx, ry, tohum, adet=60, r=(8, 13), golge=True):
    rnd = random.Random(tohum * 7 + 1)
    if golge:
        k.elips(cx - rx, cy - ry + 4, cx + rx, cy + ry + 4, TUY_K)
    k.elips(cx - rx, cy - ry, cx + rx, cy + ry, TUY)
    # Kabarik kenar: siluet boyunca yumaklar (duz elips gibi durmasin)
    n = max(10, int((rx + ry) / 9))
    for i in range(n):
        a = 2 * math.pi * i / n + rnd.uniform(-0.1, 0.1)
        yr = rnd.uniform(r[0], r[1]) * 1.1
        x, y = cx + math.cos(a) * (rx - yr * 0.4), cy + math.sin(a) * (ry - yr * 0.4)
        k.elips(x - yr, y - yr, x + yr, y + yr, TUY)
    _kivircik(k, cx, cy, rx * 0.95, ry * 0.95, tohum, adet, r)


# ------------------------------------------------------------- katmanlar
@lru_cache(maxsize=64)
def _kuyruk(aci: int):
    """Govdenin arkasinda, sagda kabarik kuyruk. aci: sallanma (derece)."""
    k = _Kalem(W, H)
    taban = (CX + 70, 560)
    r = math.radians(-35 + aci)
    pts = [(taban[0] + math.sin(r) * 60 * t + 30 * t * t, taban[1] - math.cos(r) * 90 * t) for t in
           (i / 6 for i in range(7))]
    for i, (x, y) in enumerate(pts):
        yr = 22 + 6 * math.sin(i / 6 * math.pi)
        k.elips(x - yr, y - yr, x + yr, y + yr, TUY_K if i < 2 else TUY)
        _kivircik(k, x, y, yr * 0.8, yr * 0.8, 500 + i, 6, (5, 8))
    return _kirp(k.bitir())


@lru_cache(maxsize=8)
def _govde(nefes: int, zipla: int):
    """Oturan govde: arka kalcalar, arka patiler, govde tuyu."""
    k = _Kalem(W, H)
    dy = -zipla
    for yon in (-1, 1):
        _tuylu_elips(k, CX + yon * 90, 548 + dy, 64, 56, 10 + yon, 35)
        _tuylu_elips(k, CX + yon * 116, 606 + dy, 36, 18, 20 + yon, 12, (5, 8))
    _tuylu_elips(k, CX, 455 + dy, 102 + nefes, 135, 30, 70)
    return _kirp(k.bitir())


@lru_cache(maxsize=8)
def _yelek(nefes: int, zipla: int):
    """Turuncu kapitone yelek (gogsu ve yanlari sarar) + siyah tasma. Dikisler yelegin icinde kalir."""
    from PIL import ImageChops, ImageDraw
    dy, s = -zipla, nefes
    k = _Kalem(W, H)
    # Tasma ve boyun alti koyu tuy (yelegin U yakasindan gorunur)
    k.elips(CX - 64, 318 + dy, CX + 64, 376 + dy, TASMA)
    # Yelek: govdeyi saran fici formu, U yaka
    yelek = (_egri((CX - 66, 344 + dy), (CX - 100, 350 + dy), (CX - 106 - s, 400 + dy))
             + _egri((CX - 106 - s, 400 + dy), (CX - 114 - s, 470 + dy), (CX - 84, 508 + dy))
             + _egri((CX - 84, 508 + dy), (CX, 548 + dy), (CX + 84, 508 + dy))
             + _egri((CX + 84, 508 + dy), (CX + 114 + s, 470 + dy), (CX + 106 + s, 400 + dy))
             + _egri((CX + 106 + s, 400 + dy), (CX + 100, 350 + dy), (CX + 66, 344 + dy))
             + _egri((CX + 66, 344 + dy), (CX, 392 + dy), (CX - 66, 344 + dy)))
    k.cokgen(yelek, YELEK)
    # Kapitone: baklava dikisler (yelek maskesiyle kirpilir)
    d = _Kalem(W, H)
    for i in range(-6, 7):
        x = CX + i * 28
        d.cizgi([(x - 60, 330 + dy), (x + 60, 540 + dy)], YELEK_K, 2)
        d.cizgi([(x + 60, 330 + dy), (x - 60, 540 + dy)], YELEK_K, 2)
    maske = Image.new("L", k.img.size, 0)
    ImageDraw.Draw(maske).polygon(k._p(yelek), fill=255)
    d.img.putalpha(ImageChops.multiply(d.img.split()[3], maske))
    k.img.alpha_composite(d.img)
    # Hacim golgesi: yanlar koyu
    g = _Kalem(W, H)
    g.elips(CX - 150, 330 + dy, CX - 70, 540 + dy, YELEK_K + (150,))
    g.elips(CX + 70, 330 + dy, CX + 150, 540 + dy, YELEK_K + (150,))
    g.img = g.img.filter(ImageFilter.GaussianBlur(12 * OLCEK))
    g.img.putalpha(ImageChops.multiply(g.img.split()[3], maske))
    k.img.alpha_composite(g.img)
    k.d = ImageDraw.Draw(k.img)
    # Kol agizlari (on bacaklarin ciktigi yer) ve alt kenar bieyi
    for yon in (-1, 1):
        k.yay((CX + yon * 44 - 30, 440 + dy, CX + yon * 44 + 30, 500 + dy), 200, 340, YELEK_K, 3)
    k.cizgi(_egri((CX - 84, 506 + dy), (CX, 544 + dy), (CX + 84, 506 + dy)), YELEK_K, 3)
    k.cizgi(_egri((CX + 66, 346 + dy), (CX, 392 + dy), (CX - 66, 346 + dy)), YELEK_K, 3)   # yaka biyesi
    k.elips(CX - 7, 368 + dy, CX + 7, 382 + dy, (205, 205, 215))   # kunye
    return _kirp(k.bitir())


@lru_cache(maxsize=128)
def _on_bacak(taraf: str, aci: int, zipla: int):
    """On bacak + pati. aci: 0 asagi, buyudukce disa/yukari kalkar (sol bacak icerige gosterir)."""
    yon = -1 if taraf == "sol" else 1
    omuz = (CX + yon * 44, 452 - zipla)
    r = math.radians(aci)
    boy = 150
    uc = (omuz[0] + yon * math.sin(r) * boy, omuz[1] + math.cos(r) * boy)
    pay = 60
    ox, oy = min(omuz[0], uc[0]) - pay, min(omuz[1], uc[1]) - pay
    k = _Kalem(abs(uc[0] - omuz[0]) + 2 * pay, abs(uc[1] - omuz[1]) + 2 * pay, ox, oy)
    k.kapsul(omuz, uc, 56, TUY_KK)   # hafif kontur: kalca tuyuyle karismasin
    k.kapsul(omuz, uc, 50, TUY)
    for i in range(7):   # bacak boyunca kabarik kivircik
        t = (i + 0.5) / 7
        x, y = omuz[0] + (uc[0] - omuz[0]) * t, omuz[1] + (uc[1] - omuz[1]) * t
        for kenar in (-1, 1):   # kenarlarda tasan yumaklar
            px, py = -(uc[1] - omuz[1]) / boy, (uc[0] - omuz[0]) / boy
            ex, ey = x + px * 22 * kenar, y + py * 22 * kenar
            k.elips(ex - 10, ey - 10, ex + 10, ey + 10, TUY)
        _kivircik(k, x, y, 20, 18, 300 + i + (0 if yon < 0 else 50), 6, (6, 10))
    # Pati
    k.elips(uc[0] - 31, uc[1] - 22, uc[0] + 31, uc[1] + 23, TUY_KK)
    k.elips(uc[0] - 28, uc[1] - 20, uc[0] + 28, uc[1] + 20, TUY)
    _kivircik(k, uc[0], uc[1], 22, 14, 400 + (0 if yon < 0 else 9), 8, (5, 8))
    if aci > 40:   # kalkik patide pati yastikciklari gorunur
        k.elips(uc[0] - 9, uc[1] - 6, uc[0] + 9, uc[1] + 8, (150, 100, 90))
        for dx in (-14, 0, 14):
            k.elips(uc[0] + dx - 5, uc[1] - 17, uc[0] + dx + 5, uc[1] - 8, (150, 100, 90))
    img, (x, y) = _kirp(k.bitir())
    return img, (int(ox) + x, int(oy) + y)


# Bas yerel tuvali: donme noktasi boyun (BX, PY)
BW, BH, BX, BY, PY = 380, 380, 190, 160, 285


@lru_cache(maxsize=512)
def _bas(agiz: int, goz_kapali: bool, kulak: int, egim: int, kas: int):
    """Kabarik bas, sarkik kulaklar, gozler, burun, agiz/dil. kulak: -2..2 sallanma."""
    k = _Kalem(BW, BH)
    c, y = BX, BY
    # Kulaklar (arka): basin yanlarindan sarkar
    for yon in (-1, 1):
        sallan = kulak * 4 * yon
        kok = (c + yon * 80, y - 30)
        r = math.radians(10 + sallan)
        uc = (kok[0] + yon * math.sin(r) * 150, kok[1] + math.cos(r) * 150)
        for i in range(7):
            t = i / 6
            x, yy = kok[0] + (uc[0] - kok[0]) * t, kok[1] + (uc[1] - kok[1]) * t
            yr = 28 + 14 * math.sin(t * math.pi)
            k.elips(x - yr, yy - yr, x + yr, yy + yr, TUY_K)
            _kivircik(k, x, yy, yr * 0.75, yr * 0.75, 600 + i + (0 if yon < 0 else 20), 5, (6, 9),
                      (TUY, TUY_K, TUY_KK))
    # Bas
    _tuylu_elips(k, c, y, 108, 102, 700, 80, (9, 14))
    # Tepe kabarik kivircik perce (alna dusen)
    _kivircik(k, c, y - 74, 80, 30, 710, 34, (10, 15))
    # Agiz bolgesi (burun cevresi acik tuy)
    k.elips(c - 48, y + 4, c + 48, y + 74, TUY_A)
    _kivircik(k, c, y + 40, 44, 30, 720, 18, (6, 9), (TUY_A, TUY_A, TUY))
    # Gozler
    ky = y - 4 - (5 if kas else 0)
    for gx in (c - 38, c + 38):
        if goz_kapali:
            k.yay((gx - 12, y - 8, gx + 12, y + 8), 20, 160, BURUN, 4)
        else:
            k.elips(gx - 12, y - 14, gx + 12, y + 10, BURUN)
            k.elips(gx - 6, y - 10, gx, y - 4, (255, 255, 255))
        k.yay((gx - 14, ky - 26, gx + 14, ky - 10), 200, 340, TUY_KK, 3)   # kas tuyu
    # Burun
    k.elips(c - 15, y + 18, c + 15, y + 40, BURUN)
    k.elips(c - 8, y + 21, c - 1, y + 27, (110, 100, 100))
    # Agiz
    if agiz == 0:
        k.cizgi(_egri((c - 22, y + 50), (c - 11, y + 60), (c, y + 48)), BURUN, 3)
        k.cizgi(_egri((c, y + 48), (c + 11, y + 60), (c + 22, y + 50)), BURUN, 3)
    else:
        acik = 22 if agiz == 1 else 34
        k.elips(c - 24, y + 44, c + 24, y + 44 + acik, (90, 30, 34))
        k.elips(c - 14, y + 44 + acik * 0.45, c + 14, y + 52 + acik + 8, DIL)
        k.cizgi([(c, y + 52 + acik * 0.5), (c, y + 48 + acik + 6)], (200, 80, 100), 2)
        k.cizgi(_egri((c - 24, y + 46), (c - 12, y + 52), (c, y + 44)), BURUN, 3)
        k.cizgi(_egri((c, y + 44), (c + 12, y + 52), (c + 24, y + 46)), BURUN, 3)
    img = k.bitir()
    if egim:
        img = img.rotate(-egim, resample=Image.BICUBIC, center=(BX, PY))
    return _kirp(img)


# ------------------------------------------------------------- kare
@dataclass
class Durum:
    agiz: int = 0
    goz_kapali: bool = False
    kas: int = 0
    egim: int = 0
    kulak: int = 0
    kuyruk: int = 0
    nefes: int = 0
    zipla: int = 0
    pati: int = 0


def kare(d: Durum) -> Image.Image:
    tuval = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def ekle(katman):
        img, (x, y) = katman
        tuval.alpha_composite(img, (x, y))

    ekle(_kuyruk(d.kuyruk))
    ekle(_govde(d.nefes, d.zipla))
    ekle(_on_bacak("sag", 4, d.zipla))
    kalkik = d.pati > 30
    if not kalkik:
        ekle(_on_bacak("sol", d.pati, d.zipla))   # bacak yelegin kol agzindan cikar
    ekle(_yelek(d.nefes, d.zipla))
    bas, (hx, hy) = _bas(d.agiz, d.goz_kapali, d.kulak, d.egim, d.kas)
    tuval.alpha_composite(bas, (CX - BX + hx, 340 - d.zipla - PY + hy))
    if kalkik:
        ekle(_on_bacak("sol", d.pati, d.zipla))   # kalkik pati onde
    return tuval


def oran() -> float:
    return max(0.4, min(1.2, float(getattr(config, "VIDEO_KARAKTER_BOYUT", 0.8))))


def boyut() -> tuple[int, int]:
    o = oran()
    return int(W * o) // 2 * 2, int(H * o) // 2 * 2


def sag_alan() -> int:
    return int(SAG_ALAN * oran())


def konum() -> tuple[int, int]:
    from services.video_builder import GENISLIK, YUKSEKLIK
    o = oran()
    return int(GENISLIK - 160 * o - CX * o), int(YUKSEKLIK - 30 - 622 * o)


def kare_ekran(d: Durum) -> Image.Image:
    img = kare(d)
    if boyut() != (W, H):
        img = img.resize(boyut(), Image.BILINEAR)
    alfa = img.split()[3]
    hale = Image.new("RGBA", img.size, (255, 255, 255, 0))
    hale.putalpha(alfa.filter(ImageFilter.GaussianBlur(3)).point(lambda a: min(255, a) * 70 // 255))
    hale.alpha_composite(img)
    return hale


def animasyon(halleri: list[str], siddet: list[float], sahne_baslari: list[float],
              cumle_baslari: list[float]):
    """Her kare icin Durum. Jestler figur ile ayni plana gore:
    goster: sol on patiyle icerige gosterme, anlat: belirgin kafa yatirma, acik: mutlu ziplama."""
    from services.figur import _jest_plani
    kare_sayisi = len(halleri)
    sure = kare_sayisi / FPS

    def konusuyor(t):
        i = int(t * FPS)
        p = siddet[max(0, i - 15):i + 15]
        return bool(p) and sum(1 for x in p if x > 0.15) > len(p) * 0.3

    plan = _jest_plani(sure, sahne_baslari, cumle_baslari, konusuyor)
    enerji = 0.0
    for i in range(kare_sayisi):
        t = i / FPS
        ad = halleri[i]
        enerji = enerji * 0.8 + (siddet[i] if i < len(siddet) else 0) * 0.2
        jest, w = None, 0.0
        for p0, p1, dj in plan:
            if p0 - 0.05 <= t <= p1 + 0.45:
                w = min(_yumusak((t - p0) / 0.4), 1 - _yumusak((t - p1) / 0.4))
                jest = dj
                break

        pati = 4
        if jest == "goster":
            pati = 4 + (112 - 4) * w + 6 * w * math.sin(2 * math.pi * 1.2 * t)
        egim = 4 * math.sin(2 * math.pi * t / 4.6) + 3 * enerji * math.sin(2 * math.pi * 1.7 * t)
        if jest == "anlat":
            egim += 11 * w          # merakli kopek kafa yatirmasi
        elif jest == "goster":
            egim -= 5 * w
        zipla = 0
        if jest == "acik":
            zipla = 10 * w * abs(math.sin(2 * math.pi * 1.6 * t))
        hiz = 3.2 if (enerji > 0.3 or jest == "acik") else 1.6
        kuyruk = 20 * math.sin(2 * math.pi * hiz * t)
        kulak = 2 * math.sin(2 * math.pi * 1.3 * t) + (2 if jest == "anlat" else 0) * w
        yield Durum(
            agiz={"kapali": 0, "kirpik": 0, "yarim": 1, "acik": 2}[ad],
            goz_kapali=ad == "kirpik",
            kas=1 if (jest in ("goster", "anlat") and w > 0.5) else 0,
            egim=max(-14, min(14, int(round(egim / 2) * 2))),
            kulak=max(-2, min(2, int(round(kulak)))),
            kuyruk=int(round(kuyruk / 4) * 4),
            nefes=int(round((1 + math.sin(2 * math.pi * t / 3.2)) * 1.5)),
            zipla=int(round(zipla / 2) * 2),
            pati=int(round(pati / 5) * 5),
        )
