"""Gosterge kartlarini modern sunum slayti olarak cizer ve anlatima gore vurgular.

Tek kart:   sol tarafta 2 sutunlu metrik kutucuklari, sagda one cikan metrik + yorum
2-3 kart:   her kart bir sutun; kutucuklar, one cikan metrik ve yorum alt alta

Vurgu: anlatici "bakiye" dediginde bakiye kutucuklari, "faiz" dediginde faiz kutucuklari
one cikar, digerleri soluklasir. Birden fazla kart varsa kart basligindaki ayirt edici
kelimeler ("Tüketici", "Ticari") gecince o karta odaklanilir.
"""
import re

from PIL import Image, ImageDraw

import config
from services.pdf_kartlar import Kart, Metrik, SayfaDuzeni
from services.video_builder import (GENISLIK, SAYFA_ALANI_ALT, YUKSEKLIK, _arka_plan, _font,
                                    _logo_yerlestir, _renk, _sar, _tr_buyuk)

YESIL, KIRMIZI = (61, 220, 151), (255, 107, 107)
ETIKET_RENGI, SOLUK = (176, 192, 212), (120, 138, 160)
DURAK = {"önceki", "günlük", "gün", "etkisi", "net", "dod", "mio", "değer", "toplam"}


# --------------------------------------------------------------- vurgu
def _normal(metin: str) -> str:
    metin = metin.replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"[^\wçğıöşü]+", " ", metin)


def _anahtarlar(metin: str, durak=DURAK) -> list[str]:
    return [k for k in _normal(metin).split() if len(k) >= 4 and k not in durak]


def _kok(kelime: str) -> str:
    return kelime[:max(4, min(len(kelime), 6))]     # Turkce ekler icin kaba kok


def _gecer_mi(anahtar: str, kelimeler: list[str]) -> bool:
    kok = _kok(anahtar)
    return any(k.startswith(kok) for k in kelimeler)


class Vurgulayici:
    """Altyazi parcalarini sirayla alir, hangi kartin/kutucuklarin vurgulanacagini soyler."""

    def __init__(self, duzen: SayfaDuzeni):
        self.duzen = duzen
        self.odak = None if len(duzen.kartlar) > 1 else 0
        basliklar = [{_kok(a) for a in _anahtarlar(k.baslik)} for k in duzen.kartlar]
        # Her kart icin sadece o karta ozgu kokler ("kredileri"/"krediler" ortak sayilir)
        self.kart_anahtar = [
            {a for a in b if not any(a in diger for j, diger in enumerate(basliklar) if j != i)}
            for i, b in enumerate(basliklar)
        ]

    def __call__(self, metin: str) -> tuple:
        kelimeler = _normal(metin).split()
        if not kelimeler:
            return (self.odak, frozenset())
        puanlar = [sum(_gecer_mi(a, kelimeler) for a in anahtarlar) for anahtarlar in self.kart_anahtar]
        en_iyi = max(puanlar) if puanlar else 0
        if en_iyi and puanlar.count(en_iyi) == 1:
            self.odak = puanlar.index(en_iyi)
        kartlar = [self.odak] if self.odak is not None else range(len(self.duzen.kartlar))
        secili = set()
        for ki in kartlar:
            for mi, m in enumerate(self.duzen.kartlar[ki].metrikler):
                if any(_gecer_mi(a, kelimeler) for a in _anahtarlar(m.etiket)):
                    secili.add((ki, mi))
        return (self.odak, frozenset(secili))


# --------------------------------------------------------------- cizim
def _acik(renk, oran):
    return tuple(int(c + (255 - c) * oran) for c in renk)


def _karisim(a, b, oran):
    return tuple(int(x + (y - x) * oran) for x, y in zip(a, b))


def _ok(d: ImageDraw.ImageDraw, x, y, boyut, yon, renk):
    if yon == "asagi":
        d.polygon([(x, y), (x + boyut, y), (x + boyut / 2, y + boyut * 0.85)], fill=renk)
    elif yon == "yukari":
        d.polygon([(x, y + boyut * 0.85), (x + boyut, y + boyut * 0.85), (x + boyut / 2, y)], fill=renk)


def _sigan_font(metin, kalin, boyut, genislik, en_kucuk=20):
    while boyut > en_kucuk:
        f = _font(kalin, boyut)
        if f.getlength(metin) <= genislik:
            return f
        boyut -= 2
    return _font(kalin, en_kucuk)


def _deger_rengi(m: Metrik):
    return {"olumlu": YESIL, "olumsuz": KIRMIZI}.get(m.renk, (255, 255, 255))


def _kutucuk(img, kutu, m: Metrik, durum: str, olcek: float, buyuk=False):
    """durum: 'normal', 'vurgulu', 'soluk'"""
    x0, y0, x1, y1 = kutu
    d = ImageDraw.Draw(img)
    zemin = _acik(_renk(config.VIDEO_BG2), 0.07)
    vurgu = _renk(config.VIDEO_ACCENT)
    if buyuk:
        zemin = _karisim(zemin, vurgu, 0.16)
    if durum == "vurgulu":
        zemin = _acik(zemin, 0.08)
    d.rounded_rectangle(kutu, radius=int(22 * olcek), fill=zemin,
                        outline=vurgu if durum == "vurgulu" else _acik(zemin, 0.1),
                        width=max(2, int((5 if durum == "vurgulu" else 2) * olcek)))
    if buyuk:
        d.rounded_rectangle([x0, y0 + 18 * olcek, x0 + 8 * olcek, y1 - 18 * olcek], radius=4, fill=vurgu)

    ic = int((34 if buyuk else 26) * olcek)
    gen = x1 - x0 - 2 * ic
    y = y0 + ic * 0.8

    # Sag ust kosede etiketcik: birim ("Mio TL", "%") ve varsa alt etiket ("Randıman Etkisi")
    etiketcikler = [t for t in (m.birim, m.alt_etiket if buyuk else "") if t]
    f_cip = _font(False, max(15, int(22 * olcek)))
    cx = x1 - ic
    for t in reversed(etiketcikler):
        w = f_cip.getlength(t) + 18 * olcek
        d.rounded_rectangle([cx - w, y - 2 * olcek, cx, y + f_cip.size + 10 * olcek],
                            radius=8, fill=_acik(zemin, 0.09))
        d.text((cx - w + 9 * olcek, y + 3 * olcek), t, font=f_cip, fill=SOLUK)
        cx -= w + 10 * olcek
    etiket_gen = cx - (x0 + ic) - 8
    hedef = int((34 if buyuk else 27) * olcek)
    f_etiket = _sigan_font(m.etiket, False, hedef, etiket_gen, 14)
    etiket_satir = [m.etiket]
    if f_etiket.size < hedef * 0.85 and " " in m.etiket:
        # Cok kuculmek yerine iki satira bol
        f_etiket = _font(False, int(hedef * 0.9))
        etiket_satir = _sar(m.etiket, f_etiket, etiket_gen, 2)
    for i, t in enumerate(etiket_satir):
        d.text((x0 + ic, y + i * f_etiket.size * 1.15), t, font=f_etiket, fill=ETIKET_RENGI)

    renk = _deger_rengi(m)
    ok_alani = int(44 * olcek) if m.yon else 0
    deger_boy = int((96 if buyuk else 62) * olcek)
    ust_bosluk = y + f_etiket.size * 1.15 * len(etiket_satir) + 10 * olcek
    alan_h = y1 - ic * 0.6 - ust_bosluk
    f_deger = _sigan_font(m.deger, True, min(deger_boy, int(alan_h / 1.05)), gen - ok_alani, 18)
    dy = y1 - ic * 0.6 - f_deger.size * 1.15
    if m.yon:
        _ok(d, x0 + ic, dy + f_deger.size * 0.38, f_deger.size * 0.5, m.yon, renk)
    d.text((x0 + ic + ok_alani, dy), m.deger, font=f_deger, fill=renk)

    if durum == "soluk":
        perde = Image.new("RGBA", (int(x1 - x0) + 1, int(y1 - y0) + 1), (0, 0, 0, 0))
        ImageDraw.Draw(perde).rounded_rectangle([0, 0, x1 - x0, y1 - y0], radius=int(22 * olcek),
                                               fill=_renk(config.VIDEO_BG) + (125,))
        img.alpha_composite(perde, (int(x0), int(y0)))


def _yorum(img, kutu, metin, olcek, soluk=False):
    if not metin:
        return
    x0, y0, x1, y1 = kutu
    d = ImageDraw.Draw(img)
    zemin = _acik(_renk(config.VIDEO_BG2), 0.04)
    d.rounded_rectangle(kutu, radius=int(18 * olcek), fill=zemin)
    d.rectangle([x0, y0 + 14, x0 + 6, y1 - 14], fill=_renk(config.VIDEO_ACCENT))
    ic = int(26 * olcek)
    boy = int(27 * olcek)
    while boy >= 16:
        f = _font(False, boy)
        satir_y = int(boy * 1.4)
        azami = max(1, int((y1 - y0 - 2 * ic + boy * 0.4) // satir_y))
        satirlar = _sar(metin, f, x1 - x0 - 2 * ic - 10, azami)
        if not satirlar[-1].endswith("…") or boy <= 18:
            break
        boy -= 2
    for i, s in enumerate(satirlar):
        d.text((x0 + ic + 10, y0 + ic + i * satir_y), s, font=f, fill=SOLUK if soluk else (225, 232, 240))


def _ust_bilgi(img, duzen, sira, toplam):
    d = ImageDraw.Draw(img)
    vurgu = _renk(config.VIDEO_ACCENT)
    x = _logo_yerlestir(img, 100, 52, (220, 50), zemin=True) if config.VIDEO_LOGO else 100
    x = x + 30 if config.VIDEO_LOGO else x
    f = _font(True, 26)
    d.text((x, 70), _tr_buyuk(duzen.ust_baslik)[:80], font=f, fill=vurgu)
    sayac = f"Sayfa {sira} / {toplam}"
    d.text((GENISLIK - 100 - f.getlength(sayac), 70), sayac, font=f, fill=(200, 210, 225))
    d.line([(100, 128), (GENISLIK - 100, 128)], fill=(70, 90, 120), width=2)


def _baslik(img, x, y, genislik, metin, boyut, soluk=False):
    d = ImageDraw.Draw(img)
    f = _sigan_font(metin, True, boyut, genislik, 24)
    d.text((x, y), metin, font=f, fill=SOLUK if soluk else (255, 255, 255))
    return y + f.size * 1.35


def _metrik_durumu(ki, mi, odak, secili):
    if (ki, mi) in secili:
        return "vurgulu"
    if secili or (odak is not None and odak != ki):
        return "soluk"
    return "normal"


def _satirlar(metrikler: list) -> list[list]:
    """Kutucuklari konuya gore satirlara gruplar: [bakiye: onceki, gunluk, degisim], [faiz: ...].
    Gruplama anlamli degilse kaynaktaki sirayla ikiserli satirlar."""
    gruplar: dict[str, list] = {}
    for mi, m in metrikler:
        anahtar = next(iter(_anahtarlar(m.etiket)), m.etiket)
        gruplar.setdefault(_kok(anahtar), []).append((mi, m))
    satirlar = list(gruplar.values())
    if 2 <= len(satirlar) <= 4 and all(1 < len(g) <= 3 for g in satirlar):
        return satirlar
    return [metrikler[i:i + 2] for i in range(0, len(metrikler), 2)]


def _izgara(img, x0, y0, x1, y1, satirlar, ki, odak, secili, azami_olcek):
    sutun = max(len(s) for s in satirlar)
    bosluk = 22
    kw = (x1 - x0 - bosluk * (sutun - 1)) / sutun
    kh = min((y1 - y0 - bosluk * (len(satirlar) - 1)) / len(satirlar), kw * 0.62)
    olcek = min(azami_olcek, kh / 175, kw / 330)
    for r, satir in enumerate(satirlar):
        for c, (mi, m) in enumerate(satir):
            kx, ky = x0 + c * (kw + bosluk), y0 + r * (kh + bosluk)
            _kutucuk(img, (kx, ky, kx + kw, ky + kh), m, _metrik_durumu(ki, mi, odak, secili), olcek)
    return y0 + len(satirlar) * (kh + bosluk) - bosluk


def sunum_slayti(duzen: SayfaDuzeni, sira: int, toplam: int, vurgu=(None, frozenset()),
                 altyazi_alani: bool = True) -> Image.Image:
    odak, secili = vurgu
    img = _arka_plan().convert("RGBA")
    _ust_bilgi(img, duzen, sira, toplam)
    ust, alt = 165, (SAYFA_ALANI_ALT - 10 if altyazi_alani else YUKSEKLIK - 70)
    bosluk = 26
    n = len(duzen.kartlar)

    if n == 1:
        kart: Kart = duzen.kartlar[0]
        y = _baslik(img, 100, ust, GENISLIK - 200, kart.baslik, 64)
        normal = [(i, m) for i, m in enumerate(kart.metrikler) if not m.one_cikan]
        onde = [(i, m) for i, m in enumerate(kart.metrikler) if m.one_cikan]
        sag_gen = 600 if (onde or kart.yorum) else 0
        sol_x1 = GENISLIK - 100 - (sag_gen + 40 if sag_gen else 0)
        if normal:
            _izgara(img, 100, y, sol_x1, alt, _satirlar(normal), 0, odak, secili, 1.0)
        sx0, sy = sol_x1 + 40, y
        for mi, m in onde:
            h = (alt - y) * (0.52 if kart.yorum else 1.0) / len(onde)
            _kutucuk(img, (sx0, sy, GENISLIK - 100, sy + h), m, _metrik_durumu(0, mi, odak, secili),
                     min(1.0, h / 330), buyuk=True)
            sy += h + bosluk
        if kart.yorum and sag_gen:
            _yorum(img, (sx0, sy, GENISLIK - 100, alt), kart.yorum, 1.0, soluk=bool(secili))
        return img.convert("RGB")

    # 2-3 kart: yan yana sutunlar
    kenar = 100 if n == 2 else 70
    ara = 56 if n == 2 else 36
    sutun = (GENISLIK - 2 * kenar - ara * (n - 1)) / n
    olcek = 0.85 if n == 2 else 0.68
    for ki, kart in enumerate(duzen.kartlar):
        x0 = kenar + ki * (sutun + ara)
        x1 = x0 + sutun
        kart_soluk = odak is not None and odak != ki
        y = _baslik(img, x0, ust, sutun, kart.baslik, 46 if n == 2 else 34, soluk=kart_soluk)
        normal = [(i, m) for i, m in enumerate(kart.metrikler) if not m.one_cikan]
        onde = [(i, m) for i, m in enumerate(kart.metrikler) if m.one_cikan]
        yorum_h = (125 if n == 2 else 135) if kart.yorum else 0
        onde_h = (150 if n == 2 else 130) * len(onde)
        izgara_alt = alt - yorum_h - onde_h - bosluk * (len(onde) + (1 if kart.yorum else 0))
        if normal:
            y = _izgara(img, x0, y, x1, izgara_alt, _satirlar(normal), ki, odak, secili, olcek) + bosluk
        for mi, m in onde:
            h = onde_h / len(onde)
            _kutucuk(img, (x0, y, x1, y + h), m, _metrik_durumu(ki, mi, odak, secili),
                     min(olcek, h / 250), buyuk=True)
            y += h + bosluk
        if kart.yorum:
            _yorum(img, (x0, y, x1, min(alt, y + yorum_h)), kart.yorum, olcek * 0.95,
                   soluk=kart_soluk or bool(secili))
    return img.convert("RGB")


class SunumCizici:
    """Video icin: her altyazi parcasinda vurguyu guncelleyip slayti cizer (onbellekli)."""

    def __init__(self, duzen: SayfaDuzeni, sira: int, toplam: int, altyazi_alani: bool):
        self.duzen, self.sira, self.toplam, self.altyazi_alani = duzen, sira, toplam, altyazi_alani
        self.vurgulayici = Vurgulayici(duzen)
        self._onbellek = {}
        self.son = (self.vurgulayici.odak, frozenset())

    def __call__(self, metin: str) -> Image.Image:
        if metin.strip():
            yeni = self.vurgulayici(metin)
            # Hicbir metrik gecmiyorsa onceki vurguyu koru (kart odagi degismis olabilir)
            self.son = yeni if (yeni[1] or yeni[0] != self.son[0]) else self.son
        if self.son not in self._onbellek:
            self._onbellek[self.son] = sunum_slayti(self.duzen, self.sira, self.toplam,
                                                    self.son, self.altyazi_alani)
        return self._onbellek[self.son]
