"""Videoda konusan 2D sunucu karakteri.

Karakter sag alt kosede durur; agzi seslendirmenin siddetine gore acilip kapanir, arada goz kirpar.
Varsayilan karakter burada kodla cizilir (ozgun tasarim). Kendi karakterinizi kullanmak icin
KARAKTER_KLASORU ayarina su PNG dosyalarini (seffaf arka planli, ayni boyutta) koyun:
    kapali.png  yarim.png  acik.png      zorunlu (agiz halleri)
    kirpik.png                            istege bagli (gozler kapali, agiz kapali)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import config

GEN, YUK = 440, 600          # sprite boyutu (videodaki boyut)
OLCEK = 3                    # kenar yumusatma icin buyuk cizip kucultme
FPS = 25
AGIZ = ("kapali", "yarim", "acik")


def _r(hex_kod):
    h = hex_kod.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _ciz(agiz: int, goz_kapali: bool) -> Image.Image:
    """Ozgun sunucu karakteri: kisa sacli, ceketli, guler yuzlu."""
    s = OLCEK
    W, H = GEN * s, YUK * s
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    vurgu = _r(config.VIDEO_ACCENT)
    ceket = (54, 66, 86)          # arka plan renginden bagimsiz, her zeminde secilebilir
    ten, ten_golge = (241, 200, 168), (222, 174, 140)
    sac = (58, 42, 36)
    cx = W // 2

    def e(x0, y0, x1, y1, **k):
        d.ellipse([x0 * s, y0 * s, x1 * s, y1 * s], **k)

    def rr(x0, y0, x1, y1, r, **k):
        d.rounded_rectangle([x0 * s, y0 * s, x1 * s, y1 * s], radius=r * s, **k)

    def poly(noktalar, **k):
        d.polygon([(x * s, y * s) for x, y in noktalar], **k)

    c = GEN // 2
    # Govde: ceket (omuzlar), gomlek yakasi, fular
    rr(c - 190, 430, c + 190, 700, 90, fill=ceket)
    poly([(c - 70, 430), (c + 70, 430), (c, 540)], fill=(245, 247, 250))          # gomlek
    poly([(c - 70, 430), (c - 18, 470), (c - 95, 560), (c - 120, 455)], fill=_acik(ceket, 0.12))  # yaka sol
    poly([(c + 70, 430), (c + 18, 470), (c + 95, 560), (c + 120, 455)], fill=_acik(ceket, 0.12))  # yaka sag
    poly([(c - 22, 455), (c + 22, 455), (c + 14, 500), (c, 545), (c - 14, 500)], fill=vurgu)     # fular
    e(c - 9, 452, c + 9, 470, fill=_koyu(vurgu, 0.2))
    # Yaka rozeti
    e(c + 95, 500, c + 117, 522, fill=vurgu)

    # Boyun
    rr(c - 38, 360, c + 38, 450, 20, fill=ten_golge)
    # Kulaklar
    e(c - 128, 225, c - 92, 295, fill=ten_golge)
    e(c + 92, 225, c + 128, 295, fill=ten_golge)
    # Bas
    e(c - 112, 120, c + 112, 400, fill=ten)
    # Sac: ust kisim ve yan ayrim
    d.chord([(c - 120) * s, 92 * s, (c + 120) * s, 300 * s], 180, 360, fill=sac)
    poly([(c - 120, 196), (c - 104, 260), (c - 92, 196)], fill=sac)
    poly([(c + 120, 196), (c + 106, 250), (c + 96, 196)], fill=sac)
    d.chord([(c - 40) * s, 120 * s, (c + 135) * s, 230 * s], 190, 330, fill=_acik(sac, 0.08))

    # Kaslar: hafif kavisli, rahat ifade
    d.arc([(c - 74) * s, 208 * s, (c - 24) * s, 232 * s], 200, 340, fill=sac, width=7 * s)
    d.arc([(c + 24) * s, 208 * s, (c + 74) * s, 232 * s], 200, 340, fill=sac, width=7 * s)

    # Gozler
    for gx in (c - 48, c + 48):
        if goz_kapali:
            d.arc([(gx - 18) * s, 240 * s, (gx + 18) * s, 268 * s], 20, 160, fill=(60, 45, 40), width=5 * s)
        else:
            e(gx - 17, 236, gx + 17, 272, fill=(255, 255, 255))
            e(gx - 10, 243, gx + 10, 267, fill=(70, 52, 44))
            e(gx - 4, 247, gx + 3, 254, fill=(255, 255, 255))

    # Burun ve yanaklar
    d.arc([(c - 14) * s, 270 * s, (c + 14) * s, 305 * s], 20, 160, fill=ten_golge, width=5 * s)
    # Yanaklar: ayri katmanda yari saydam (dogrudan cizmek yuzu saydamlastirir)
    allik = Image.new("RGBA", img.size, (0, 0, 0, 0))
    da = ImageDraw.Draw(allik)
    da.ellipse([(c - 92) * s, 292 * s, (c - 58) * s, 316 * s], fill=(240, 150, 140, 90))
    da.ellipse([(c + 58) * s, 292 * s, (c + 92) * s, 316 * s], fill=(240, 150, 140, 90))
    img.alpha_composite(allik)
    d = ImageDraw.Draw(img)

    # Agiz
    dudak = (170, 72, 70)
    if agiz == 0:
        d.arc([(c - 34) * s, 300 * s, (c + 34) * s, 345 * s], 25, 155, fill=dudak, width=6 * s)
    elif agiz == 1:
        e(c - 26, 318, c + 26, 350, fill=(110, 38, 40))
        e(c - 15, 334, c + 15, 350, fill=(222, 110, 110))
    else:
        e(c - 32, 312, c + 32, 370, fill=(110, 38, 40))
        d.chord([(c - 26) * s, 312 * s, (c + 26) * s, 336 * s], 0, 180, fill=(255, 255, 255))
        e(c - 18, 348, c + 18, 368, fill=(222, 110, 110))

    img = img.resize((GEN, YUK), Image.LANCZOS)
    alfa = img.split()[3]
    # Ince acik kontur: koyu zeminlerde siluet kaybolmasin
    kontur = Image.new("RGBA", img.size, (255, 255, 255, 0))
    kontur.putalpha(alfa.filter(ImageFilter.MaxFilter(7)).point(lambda a: 110 if a > 40 else 0))
    # Hafif golge: acik zeminlerde de karakter one ciksin
    golge = Image.new("RGBA", img.size, (0, 0, 0, 0))
    golge.putalpha(alfa.point(lambda a: a * 70 // 255))
    golge = golge.filter(ImageFilter.GaussianBlur(10))
    sonuc = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sonuc.alpha_composite(golge, (6, 6))
    sonuc.alpha_composite(kontur)
    sonuc.alpha_composite(img)
    return sonuc


def _acik(renk, oran):
    return tuple(int(x + (255 - x) * oran) for x in renk)


def _koyu(renk, oran):
    return tuple(int(x * (1 - oran)) for x in renk)


def sprite_seti() -> dict[str, Image.Image]:
    """{'kapali','yarim','acik','kirpik'} -> RGBA gorseller (GEN x YUK)."""
    klasor = Path(config.KARAKTER_KLASORU) if config.KARAKTER_KLASORU else None
    if klasor and all((klasor / f"{a}.png").exists() for a in AGIZ):
        set_ = {}
        for ad in AGIZ + ("kirpik",):
            yol = klasor / f"{ad}.png"
            if yol.exists():
                im = Image.open(yol).convert("RGBA")
                oran = min(GEN / im.width, YUK / im.height)   # kucuk gorselleri de alana buyut
                im = im.resize((round(im.width * oran), round(im.height * oran)), Image.LANCZOS)
                tuval = Image.new("RGBA", (GEN, YUK), (0, 0, 0, 0))
                tuval.alpha_composite(im, ((GEN - im.width) // 2, YUK - im.height))
                set_[ad] = tuval
        set_.setdefault("kirpik", set_["kapali"])
        return set_
    return {"kapali": _ciz(0, False), "yarim": _ciz(1, False), "acik": _ciz(2, False),
            "kirpik": _ciz(0, True)}


def konum() -> tuple[int, int]:
    """Karakterin videodaki sol ust kosesi (sag alt koseye yaslanir)."""
    from services.video_builder import GENISLIK, YUKSEKLIK
    return GENISLIK - GEN - 30, YUKSEKLIK - YUK + 20   # alt kisim biraz disari tasar (busto)


def ses_siddeti(wav_yolu: Path) -> list[float]:
    """Her video karesi icin normallestirilmis ses siddeti (0 sessiz, ~1 yuksek)."""
    import wave

    import numpy as np

    with wave.open(str(wav_yolu), "rb") as w:
        hz = w.getframerate()
        ses = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    adim = hz // FPS
    kare = max(1, len(ses) // adim)
    rms = np.array([np.sqrt(np.mean(ses[i * adim:(i + 1) * adim] ** 2) + 1e-9) for i in range(kare)])
    tavan = np.percentile(rms, 95) or 1.0
    return [float(x) for x in np.minimum(rms / tavan, 1.5)]


def agiz_halleri(wav_yolu: Path, oran: list[float] | None = None) -> list[str]:
    """Her video karesi icin sprite adi: ses siddetine gore agiz, arada goz kirpma."""
    if oran is None:
        oran = ses_siddeti(wav_yolu)

    halleri, ayni = [], 0
    for i, o in enumerate(oran):
        h = 0 if o < 0.08 else (1 if o < 0.45 else 2)
        # Uzun sesli harflerde agiz donmus gibi durmasin: arada yarim aciga gec
        if halleri and h == halleri[-1] and h > 0:
            ayni += 1
            if ayni % 5 == 4:
                h = 1 if h == 2 else 2
        else:
            ayni = 0
        halleri.append(h)
    # Tek karelik titremeleri yumusat
    for i in range(1, len(halleri) - 1):
        if halleri[i - 1] == halleri[i + 1] != halleri[i]:
            halleri[i] = halleri[i - 1]

    adlar = [AGIZ[h] for h in halleri]
    # Goz kirpma: ~3-5 sn'de bir, 3 kare; sadece agiz kapaliyken (kirpik sprite'i agzi kapali)
    sonraki = int(FPS * 2.5)
    i = 0
    while i < len(adlar):
        if i >= sonraki and adlar[i] == "kapali":
            for j in range(i, min(i + 3, len(adlar))):
                if adlar[j] == "kapali":
                    adlar[j] = "kirpik"
            sonraki = i + int(FPS * (3 + (i * 7919 % 20) / 10))   # 3-5 sn, deterministik
        i += 1
    return adlar
