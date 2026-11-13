"""Fotograftan konusan karakter: yuz yuvarlak cerceve icinde, agiz sesle acilir, goz kirpar, bas hafifce oynar.

Fotograf .env'deki KARAKTER_FOTO yolundan okunur (repoya konmaz). Gozler ve agiz otomatik bulunur:
  - dudaklar: yuz derisinden belirgin kirmizi bolge (YCrCb)
  - gozler: dudaklarin ustunde, yuzdeki iki koyu bolge
Bulunamazsa veya yanlis bulunursa .env'de KARAKTER_FOTO_NOKTALAR ile verilebilir:
  KARAKTER_FOTO_NOKTALAR=sol_goz_x,sol_goz_y;sag_goz_x,sag_goz_y;agiz_x,agiz_y   (fotograf pikselleri)

Agiz acma: dudak cizgisinin altindaki bolge (alt dudak, cene) asagi kaydirilir, aradaki bosluk agiz ici
rengiyle (ust dislerin hafif izi ile) doldurulur. Goz kirpma: goz ustundeki kapak derisi gozun uzerine uzatilir.
Video ile ayni arayuz: FPS, boyut, konum, sag_alan, kare_ekran, animasyon.
"""
import math
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import config

FPS = 25
SEVIYE = 6           # agiz acikligi kademesi (0 kapali ... 5 en acik); kademe arttikca gecis yumusar
CAP = 360            # oran 1.0'da cerceve capi (piksel)
HALKA = 7            # beyaz halka kalinligi
GOLGE = 18           # golge payi


class FotoHatasi(Exception):
    pass


@dataclass(frozen=True)
class Noktalar:
    sol_goz: tuple[float, float]
    sag_goz: tuple[float, float]
    agiz: tuple[float, float]
    agiz_gen: float          # agiz genisligi (piksel)
    dudak_yuk: float         # dudaklarin toplam yuksekligi
    egri: tuple[float, float, float]   # dudak ayrim cizgisi: y = a*(x-mx)^2 + b*(x-mx) + c


@dataclass
class Durum:
    agiz: int            # 0 kapali ... SEVIYE-1 en acik
    goz_kapali: bool
    aci: float           # bas egimi (derece)
    dy: float            # dikey salinim (piksel, cikti olceginde)


# ------------------------------------------------------------ yardimcilar
def _bilesenler(maske: np.ndarray, en_az: int = 10) -> list[np.ndarray]:
    """4-komsulukla bagli bilesenler; her biri (N, 2) [y, x] dizisi. Kucuk maskeler icin (BFS)."""
    h, w = maske.shape
    gorulen = np.zeros_like(maske, dtype=bool)
    sonuc = []
    for y0, x0 in zip(*np.nonzero(maske)):
        if gorulen[y0, x0]:
            continue
        kuyruk = deque([(y0, x0)])
        gorulen[y0, x0] = True
        noktalar = []
        while kuyruk:
            y, x = kuyruk.popleft()
            noktalar.append((y, x))
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < h and 0 <= xx < w and maske[yy, xx] and not gorulen[yy, xx]:
                    gorulen[yy, xx] = True
                    kuyruk.append((yy, xx))
        if len(noktalar) >= en_az:
            sonuc.append(np.array(noktalar))
    return sonuc


def _ac(maske: np.ndarray, r: int = 1) -> np.ndarray:
    """Morfolojik acma (gurultu temizligi)."""
    im = Image.fromarray((maske * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MinFilter(2 * r + 1)).filter(ImageFilter.MaxFilter(2 * r + 1))
    return np.asarray(im) > 127


def _ycrcb(a: np.ndarray):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return y, (r - y) * 0.713 + 128, (b - y) * 0.564 + 128


def _arka_plan_maskesi(a: np.ndarray) -> np.ndarray:
    """Kenarlara bagli, cok koyu (siyah) veya cok acik (beyaz) duz zemin. Yoksa hepsi False."""
    L = a.sum(2)
    sonuc = np.zeros(L.shape, dtype=bool)
    for aday in (L < 14, L > 750):
        kenar = np.concatenate([aday[0], aday[-1], aday[:, 0], aday[:, -1]])
        if kenar.mean() < 0.5:
            continue
        # kenardan tasma doldurma (PIL floodfill ile hizli)
        im = Image.fromarray(aday.astype(np.uint8) * 255).copy()   # copy: fromarray salt okunur olabilir
        h, w = aday.shape
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            if im.getpixel((x, y)) == 255:
                ImageDraw.floodfill(im, (x, y), 128)
        for x in range(0, w, 8):
            for y in (0, h - 1):
                if im.getpixel((x, y)) == 255:
                    ImageDraw.floodfill(im, (x, y), 128)
        for y in range(0, h, 8):
            for x in (0, w - 1):
                if im.getpixel((x, y)) == 255:
                    ImageDraw.floodfill(im, (x, y), 128)
        sonuc |= np.asarray(im) == 128
    return sonuc


# ------------------------------------------------------------ yuz noktalarini bulma
def _elle_noktalar() -> tuple | None:
    ham = (getattr(config, "KARAKTER_FOTO_NOKTALAR", "") or "").strip()
    if not ham:
        return None
    try:
        p = [tuple(float(v) for v in parca.split(",")) for parca in ham.replace(" ", "").split(";")]
        assert len(p) == 3 and all(len(x) == 2 for x in p)
        return p
    except (ValueError, AssertionError):
        raise FotoHatasi("KARAKTER_FOTO_NOKTALAR şu biçimde olmalı: "
                         "sol_goz_x,sol_goz_y;sag_goz_x,sag_goz_y;agiz_x,agiz_y (ör. 380,154;449,153;418,232)")


def _dudak_egrisi(Y: np.ndarray, mx: float, my: float, gen: float, yuk: float):
    """Dudak ayrim cizgisi: her sutunda dudak bolgesindeki en koyu satir; ikinci derece egriye oturtulur."""
    xs, ys = [], []
    y0, y1 = int(my - yuk * 0.45), int(my + yuk * 0.45) + 1
    for x in range(int(mx - gen * 0.4), int(mx + gen * 0.4) + 1):
        if 0 <= x < Y.shape[1] and y0 >= 0 and y1 <= Y.shape[0] and y1 > y0:
            xs.append(x - mx)
            ys.append(y0 + int(np.argmin(Y[y0:y1, x])))
    if len(xs) < 5:
        return (0.0, 0.0, my)
    a, b, c = np.polyfit(xs, ys, 2)
    a = float(np.clip(a, -0.02, 0.02))       # asiri egriligi engelle
    return (a, float(b), float(c))


def noktalari_bul(img: Image.Image) -> Noktalar:
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    Y, Cr, Cb = _ycrcb(a)
    elle = _elle_noktalar()

    deri = (Cr > 133) & (Cr < 178) & (Cb > 78) & (Cb < 132) & (Y > 60)
    deri &= ~_arka_plan_maskesi(a)
    deri = _ac(deri, 2)
    if deri.sum() < 500 and not elle:
        raise FotoHatasi("Fotoğrafta yüz bulunamadı. KARAKTER_FOTO_NOKTALAR ile göz ve ağız konumlarını verin.")
    cr_deri = float(np.median(Cr[deri])) if deri.any() else 148.0

    if elle:
        (lx, ly), (rx, ry), (mx, my) = elle
        ipd = math.hypot(rx - lx, ry - ly)
        gen, yuk = ipd * 0.82, ipd * 0.32
    else:
        # --- dudaklar: deriden belirgin kirmizi, yuz bolgesinde en buyuk bilesen
        ys, xs = np.nonzero(deri)
        ust, alt = ys.min(), ys.max()
        dudak = (Cr > cr_deri + 12) & (Y > 45)
        dudak[: ust + int((alt - ust) * 0.12)] = False
        dudak = _ac(dudak, 1)
        adaylar = _bilesenler(dudak, en_az=60)
        if not adaylar:
            raise FotoHatasi("Fotoğrafta dudaklar bulunamadı. KARAKTER_FOTO_NOKTALAR ile göz ve ağız "
                             "konumlarını verin.")
        # yatay ve en buyuk aday
        adaylar.sort(key=lambda p: -len(p) * min(2.0, (np.ptp(p[:, 1]) + 1) / (np.ptp(p[:, 0]) + 1)))
        d = adaylar[0]
        my, mx = float(d[:, 0].mean()), float(d[:, 1].mean())
        gen, yuk = float(np.ptp(d[:, 1]) + 1), float(np.ptp(d[:, 0]) + 1)

        # --- gozler: dudaklarin ustunde, merkezin iki yaninda koyu bolgeler (alttaki = goz, ustteki = kas)
        r0, r1 = int(my - 3.4 * gen), int(my - 1.1 * gen)
        c0, c1 = int(mx - 1.9 * gen), int(mx + 1.9 * gen)
        r0, c0 = max(r0, 0), max(c0, 0)
        bolge = Y[r0:r1, c0:c1]
        if bolge.size == 0:
            raise FotoHatasi("Gözler bulunamadı. KARAKTER_FOTO_NOKTALAR ile konumları verin.")
        esik = np.percentile(bolge, 14)
        koyu = (bolge < esik) & ~_arka_plan_maskesi(a)[r0:r1, c0:c1]
        koyu = _ac(koyu, 1)
        gozler = {}
        for p in _bilesenler(koyu, en_az=12):
            py, px = p[:, 0] + r0, p[:, 1] + c0
            g, h = np.ptp(px) + 1, np.ptp(py) + 1
            if g < 0.18 * gen or h > g * 1.3:
                continue
            taraf = "sol" if px.mean() < mx else "sag"
            mevcut = gozler.get(taraf)
            if mevcut is None or py.mean() > mevcut[1]:      # en alttaki koyu bolge goz
                gozler[taraf] = (float(px.mean()), float(py.mean()))
        if len(gozler) < 2:
            raise FotoHatasi("Gözler bulunamadı. KARAKTER_FOTO_NOKTALAR ile konumları verin.")
        (lx, ly), (rx, ry) = gozler["sol"], gozler["sag"]
        ipd = math.hypot(rx - lx, ry - ly)
        # agiz merkezi yatayda gozlerin ortasina hizalanir (isik farki dudak kenarini kaydirabilir)
        mx = (lx + rx) / 2 * 0.6 + mx * 0.4
        gen = max(gen, ipd * 0.78)

    egri = _dudak_egrisi(Y, mx, my, gen, max(yuk, ipd * 0.25))
    return Noktalar((lx, ly), (rx, ry), (mx, egri[2]), gen, yuk, egri)


# ------------------------------------------------------------ hazirlik
def oran() -> float:
    return max(0.4, min(1.2, float(getattr(config, "VIDEO_KARAKTER_BOYUT", 0.8))))


def cap() -> int:
    return int(CAP * oran()) // 2 * 2


def boyut() -> tuple[int, int]:
    d = cap() + 2 * GOLGE
    return d, d


def sag_alan() -> int:
    return cap() + 70


def konum() -> tuple[int, int]:
    from services.video_builder import GENISLIK, YUKSEKLIK
    w, h = boyut()
    return GENISLIK - w - 40 + GOLGE, YUKSEKLIK - h - 40 + GOLGE


def foto_yolu() -> Path | None:
    yol = getattr(config, "KARAKTER_FOTO", None)
    return Path(yol) if yol and Path(yol).exists() else None


def tanimli_mi() -> bool:
    return foto_yolu() is not None


def _zemin_rengi():
    deger = (getattr(config, "KARAKTER_FOTO_ZEMIN", "") or "").strip().lower()
    if deger in ("orijinal", "original", "yok"):
        return None
    from PIL import ImageColor
    try:
        return ImageColor.getrgb(deger or "#EEF2F7")[:3]
    except ValueError:
        return (238, 242, 247)


@lru_cache(maxsize=2)
def _hazirla(yol: str, cap_px: int):
    """Fotografi kirpar, olcekler; 3 agiz x 2 goz halini uretir. Doner: (haller, merkez, olcek bilgisi)."""
    img = Image.open(yol).convert("RGB")
    n = noktalari_bul(img)
    a = np.asarray(img).astype(np.float32)
    zemin = _arka_plan_maskesi(a)

    ipd = math.hypot(n.sag_goz[0] - n.sol_goz[0], n.sag_goz[1] - n.sol_goz[1])
    cx = (n.sol_goz[0] + n.sag_goz[0]) / 2 * 0.5 + n.agiz[0] * 0.5
    # kadraj: sacin ustu ile omuz / bluz ust kismi cerceveye girsin
    cy = (n.sol_goz[1] + n.sag_goz[1]) / 4 + n.agiz[1] / 2 + ipd * 0.5
    R = ipd * 2.85
    # Donme ve salinimda kenar acilmasin diye %12 pay
    pay = R * 1.12
    kutu = (cx - pay, cy - pay, cx + pay, cy + pay)
    S = int(round(cap_px * 1.12 / 2)) * 2
    olcek = S / (2 * pay)

    # kenardaki koyu sacak kalmasin: maske 1 px daraltilip yumusatilir
    alfa = Image.fromarray(((~zemin) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))
    alfa = alfa.filter(ImageFilter.GaussianBlur(1.2))
    rgba = img.convert("RGBA")
    rgba.putalpha(alfa)
    kirp = rgba.transform((S, S), Image.EXTENT, kutu, Image.BICUBIC, fillcolor=(0, 0, 0, 0))

    def yerel(p):
        return ((p[0] - kutu[0]) * olcek, (p[1] - kutu[1]) * olcek)

    m = yerel(n.agiz)
    gozler = (yerel(n.sol_goz), yerel(n.sag_goz))
    ipd_s = ipd * olcek
    egri = (n.egri[0] / olcek, n.egri[1], 0.0)     # egri yerel olcekte (x ve y ayni olcekte)
    gen_s = n.agiz_gen * olcek
    taban = np.asarray(kirp).astype(np.float32)
    haller = {}
    for ag in range(SEVIYE):
        agizli = _agiz_ac(taban, m, gen_s, egri, ag)
        for kapali in (False, True):
            arr = _goz_kapat(agizli, gozler, ipd_s) if kapali else agizli
            haller[(ag, kapali)] = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    return haller, S


# ------------------------------------------------------------ agiz ve goz
def _ornekle(arr: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Cift dogrusal ornekleme (bilinear)."""
    h, w = arr.shape[:2]
    xs = np.clip(xs, 0, w - 1.001)
    ys = np.clip(ys, 0, h - 1.001)
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = (xs - x0)[..., None], (ys - y0)[..., None]
    a = arr[y0, x0] * (1 - fx) + arr[y0, x0 + 1] * fx
    b = arr[y0 + 1, x0] * (1 - fx) + arr[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def _yumusak(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _agiz_ac(arr: np.ndarray, merkez, gen: float, egri, seviye: int) -> np.ndarray:
    if seviye == 0:
        return arr.copy()
    oran_ = seviye / (SEVIYE - 1)
    acik = 0.21 * gen * oran_                      # en genis yerde agiz acikligi
    h, w = arr.shape[:2]
    mx, my = merkez
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (xx - mx) / (gen * 0.5)
    cizgi = my + egri[0] * (xx - mx) ** 2 + egri[1] * (xx - mx)       # dudak ayrim cizgisi
    # agiz boslugunun yatay profili (mercek bicimi); hareket agiz koselerinin biraz disinda biter,
    # yanaklar ve yuz kenari yerinde kalir (kayma olmasin)
    profil = np.sqrt(np.clip(1 - u ** 2, 0, 1))
    yatay = 1 - _yumusak((np.abs(u) - 0.75) / 0.55)
    asagi = acik * np.maximum(profil, yatay * 0.55)
    # dikey: alt dudak tam kayar, cene ~%30 kayar, boyun hic kaymaz
    dudak_alt = cizgi + gen * 0.32
    cene = cizgi + gen * 0.95
    t1 = _yumusak((yy - dudak_alt) / (cene - dudak_alt))           # 0 dudakta, 1 cenede
    t2 = _yumusak((yy - cene) / (gen * 0.6))                         # 1 cenenin altinda
    zayif = (1 - t1 * 0.7) * (1 - t2)
    kayma = asagi * zayif
    yukari = acik * 0.07 * profil                                     # ust dudak cok az kalkar
    ust_zayif = 1 - _yumusak((cizgi - yy) / (gen * 0.3))

    alt_bolge = yy >= cizgi
    kaynak_y = np.where(alt_bolge, yy - kayma, yy + yukari * ust_zayif)
    sonuc = _ornekle(arr, xx, kaynak_y)

    # agiz ici: ust dudak (cizgi - yukari) ile kaydirilmis alt dudak (cizgi + asagi) arasi
    ic_ust = cizgi - yukari
    ic_alt = cizgi + acik * profil
    ic = (yy > ic_ust) & (yy < ic_alt) & (profil > 0)
    derinlik = np.clip((yy - ic_ust) / np.maximum(ic_alt - ic_ust, 1e-3), 0, 1)
    # agiz ici: ustte koyu kirmizi-kahve, derine dogru koyulasir; kenarlara dogru golge
    ust_renk = np.array([96, 38, 42], np.float32)
    alt_renk = np.array([52, 18, 22], np.float32)
    renk = ust_renk * (1 - derinlik[..., None]) + alt_renk * derinlik[..., None]
    renk = renk * (0.62 + 0.38 * _yumusak(profil / 0.8))[..., None]
    # dil: acik agizda altta hafif pembe
    if oran_ > 0.6:
        dil = _yumusak((derinlik - 0.62) / 0.3) * _yumusak((profil - 0.35) / 0.4)
        renk = renk * (1 - dil[..., None] * 0.55) + np.array([150, 70, 76], np.float32) * dil[..., None] * 0.55
    # ust disler: ust dudagin hemen altinda, mercek bicimini izleyen yumusak kenarli serit
    bosluk = np.maximum(ic_alt - ic_ust, 1e-3)
    dis_boy = 0.42 - 0.12 * oran_
    dis = (1 - _yumusak((derinlik - dis_boy) / 0.14)) * _yumusak((profil - 0.42) / 0.3)
    dis = dis * _yumusak((yy - ic_ust) / np.maximum(bosluk * 0.08, 0.6))
    golgeli = np.array([228, 222, 214], np.float32) * (0.78 + 0.22 * profil)[..., None]
    golgeli = golgeli * (1 - 0.25 * derinlik[..., None] / max(dis_boy, 1e-3))
    renk = renk * (1 - dis[..., None] * 0.85) + golgeli * dis[..., None] * 0.85
    # yumusak kenar
    kenar = np.minimum(_yumusak((yy - ic_ust) / 1.2), _yumusak((ic_alt - yy) / 1.6))
    kenar = kenar * _yumusak((profil - 0.02) / 0.15)
    kenar = np.where(ic, kenar, 0)[..., None]
    sonuc[..., :3] = sonuc[..., :3] * (1 - kenar) + renk * kenar
    sonuc[..., 3] = np.maximum(sonuc[..., 3], kenar[..., 0] * 255)
    return sonuc


def _goz_kapat(arr: np.ndarray, gozler, ipd: float) -> np.ndarray:
    """Ust goz kapagi derisi (gozun hemen ustu, kasin altinda) gozun uzerine gerilir, kirpik cizgisi cizilir."""
    sonuc = arr.copy()
    h, w = arr.shape[:2]
    gy, gx = ipd * 0.085, ipd * 0.20           # goz yari yukseklik / yari genislik
    for ex, ey in gozler:
        x0, x1 = int(ex - gx * 1.6), int(ex + gx * 1.6) + 1
        y0, y1 = int(ey - gy * 2.4), int(ey + gy * 2.0) + 1
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        ust, alt = ey - gy * 1.25, ey + gy * 1.0        # kapanacak bolge: kapak kivrimi -> alt kirpik
        kaynak_ust, kaynak_alt = ey - gy * 2.1, ey - gy * 1.3   # kapak derisi bandi
        t = np.clip((yy - ust) / (alt - ust), 0, 1)
        kaynak = kaynak_ust + t * (kaynak_alt - kaynak_ust)
        cekilmis = _ornekle(arr, xx, kaynak)
        # elips bicimli harmanlama (goz bicimi)
        e = ((xx - ex) / (gx * 1.2)) ** 2 + ((yy - (ust + alt) / 2) / ((alt - ust) * 0.72)) ** 2
        k = (1 - _yumusak((e - 0.7) / 0.35))[..., None]
        bolge = sonuc[y0:y1, x0:x1]
        bolge[:] = bolge * (1 - k) + cekilmis * k
        # kapali kirpik cizgisi: hafif asagi kavisli
        kavis = alt - gy * 0.45 + ((xx - ex) / gx) ** 2 * gy * -0.35
        cizgi = np.exp(-((yy - kavis) / (gy * 0.28)) ** 2) * \
            (1 - _yumusak((np.abs(xx - ex) - gx * 0.8) / (gx * 0.3)))
        koyu = (cizgi * 0.6)[..., None]
        bolge[..., :3] = bolge[..., :3] * (1 - koyu) + np.array([58, 40, 36], np.float32) * koyu
    return sonuc


# ------------------------------------------------------------ kare cizimi
@lru_cache(maxsize=4)
def _cerceve(cap_px: int, zemin):
    """Yuvarlak maske, zemin, halka ve golge katmanlari."""
    d = cap_px
    W = d + 2 * GOLGE
    ss = 3
    m = Image.new("L", (d * ss, d * ss), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d * ss - 1, d * ss - 1), fill=255)
    maske = m.resize((d, d), Image.LANCZOS)

    golge = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gm = Image.new("L", (W, W), 0)
    gm.paste(maske, (GOLGE, GOLGE + 6))
    golge.putalpha(gm.filter(ImageFilter.GaussianBlur(10)).point(lambda v: v * 70 // 255))

    halka = Image.new("RGBA", (d * ss, d * ss), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halka)
    hd.ellipse((0, 0, d * ss - 1, d * ss - 1), outline=(255, 255, 255, 255), width=HALKA * ss)
    from PIL import ImageColor
    try:
        vurgu = ImageColor.getrgb(config.VIDEO_ACCENT)[:3]
    except (ValueError, AttributeError):
        vurgu = (46, 196, 182)
    i = HALKA * ss
    hd.ellipse((i, i, d * ss - 1 - i, d * ss - 1 - i), outline=vurgu + (255,), width=2 * ss)
    halka = halka.resize((d, d), Image.LANCZOS)

    arka = None
    if zemin is not None:
        # hafif dikey gecisli zemin
        ust = np.array(zemin, np.float32)
        alt = ust * 0.88
        t = np.linspace(0, 1, d)[:, None, None]
        g = np.broadcast_to(ust * (1 - t) + alt * t, (d, d, 3))
        arka = Image.fromarray(g.astype(np.uint8), "RGB").convert("RGBA")
    return maske, golge, halka, arka


def kare_ekran(d: Durum) -> Image.Image:
    yol = foto_yolu()
    if yol is None:
        raise FotoHatasi("KARAKTER_FOTO bulunamadı.")
    c = cap()
    haller, S = _hazirla(str(yol), c)
    kisi = haller[(d.agiz, d.goz_kapali)]
    # bas hareketi: boyun hizasi etrafinda hafif donme ve salinim
    if abs(d.aci) > 0.05 or abs(d.dy) > 0.05:
        kisi = kisi.rotate(d.aci, resample=Image.BICUBIC, center=(S / 2, S * 0.78),
                           translate=(0, d.dy))
    o = (S - c) // 2
    kisi = kisi.crop((o, o, o + c, o + c))
    maske, golge, halka, arka = _cerceve(c, _zemin_rengi())
    ic = arka.copy() if arka is not None else Image.new("RGBA", (c, c), (0, 0, 0, 255))
    ic.alpha_composite(kisi)
    ic.putalpha(maske)
    ic.alpha_composite(halka)
    tuval = golge.copy()
    tuval.alpha_composite(ic, (GOLGE, GOLGE))
    return tuval


def animasyon(halleri: list[str], siddet: list[float], sahne_baslari: list[float],
              cumle_baslari: list[float]):
    """Her kare icin Durum. Agiz acikligi ses siddetinden surekli hesaplanir, yumusatilir ve SEVIYE
    kademeye bolunur (kapali/yarim/acik arasinda sicrama olmaz). Goz kirpma halleri'nden ('kirpik')."""
    enerji, acik = 0.0, 0.0
    cumleler = sorted(cumle_baslari)
    for i, ad in enumerate(halleri):
        t = i / FPS
        s = siddet[i] if i < len(siddet) else 0.0
        enerji = enerji * 0.9 + s * 0.1
        hedef = 0.0 if s < 0.08 else min(1.0, (s - 0.08) / 0.75)
        acik += (hedef - acik) * (0.65 if hedef > acik else 0.45)     # hizli acilir, biraz yavas kapanir
        kademe = int(round(acik * (SEVIYE - 1)))
        # cumle basinda kucuk bir bas onaylama
        vurgu = 0.0
        for cb in cumleler:
            if 0 <= t - cb < 0.8:
                vurgu = math.sin(math.pi * (t - cb) / 0.8)
                break
            if cb > t:
                break
        aci = 0.9 * math.sin(2 * math.pi * t / 5.3) + 0.7 * enerji * math.sin(2 * math.pi * 0.9 * t)
        dy = 1.0 * math.sin(2 * math.pi * t / 3.4) + 2.0 * vurgu * oran()
        yield Durum(agiz=kademe, goz_kapali=ad == "kirpik", aci=round(aci, 2), dy=round(dy, 1))


def onizleme() -> Image.Image:
    """Arayuz icin: kapali, yarim, acik agiz ve goz kirpma halleri yan yana."""
    kareler = [kare_ekran(Durum(a, g, 0, 0))
               for a, g in ((0, False), (SEVIYE // 2, False), (SEVIYE - 1, False), (0, True))]
    w, h = kareler[0].size
    tuval = Image.new("RGBA", (w * 4, h), (255, 255, 255, 0))
    for i, k in enumerate(kareler):
        tuval.alpha_composite(k, (i * w, 0))
    return tuval
