"""PDF sayfasindaki gosterge kartlarini (KPI kartlari) okur.

Beklenen duzen (rapor sablonu):
    +---------------------------+
    |      TL Vadeli Mevduat    |   <- dolgulu baslik bandi
    | Onceki Gun Bakiye  Gunluk |   <- etiket (+ alt satirda birim: "(Mio TL)")
    |   1.321.572     1.266.637 |   <- kalin deger (renk ve ok isareti olabilir)
    |         ...               |
    |    Net Randiman Etkisi    |   <- ortada tek basina duran deger = one cikan metrik
    |         18,1647           |
    |  Faiz oranlarindaki ...   |   <- yorum paragrafi
    +---------------------------+

Rakamlar ve renkler PDF'ten oldugu gibi alinir; LLM'e hic gonderilmez.
Kart bulunamazsa None doner ve sayfa gorseli kullanilir.
"""
import re
from dataclasses import dataclass, field
from io import BytesIO

DEGER = re.compile(r"^[▲▼△▽↑↓]?\s*[-+−]?\d[\d.,]*\s*%?$")
OK_ASAGI, OK_YUKARI = set("▼▽↓"), set("▲△↑")


@dataclass
class Metrik:
    etiket: str
    birim: str
    deger: str
    renk: str = "notr"        # "olumlu" (yesil), "olumsuz" (kirmizi), "notr"
    yon: str = ""             # "asagi", "yukari" veya ""
    alt_etiket: str = ""
    one_cikan: bool = False   # kartin ortasinda tek basina duran metrik


@dataclass
class Kart:
    baslik: str
    metrikler: list = field(default_factory=list)
    yorum: str = ""


@dataclass
class SayfaDuzeni:
    ust_baslik: str
    kartlar: list = field(default_factory=list)


@dataclass
class _Parca:
    metin: str
    x0: float
    x1: float
    top: float
    bottom: float
    kalin: bool
    renk: tuple | None

    @property
    def xc(self):
        return (self.x0 + self.x1) / 2


# ------------------------------------------------------------------ yardimci
def _rgb(renk) -> tuple | None:
    """pdfplumber renk degerini (gri / RGB / CMYK) 0-1 RGB'ye cevirir."""
    if renk is None:
        return None
    if isinstance(renk, (int, float)):
        renk = (renk,)
    try:
        renk = tuple(float(x) for x in renk)
    except (TypeError, ValueError):
        return None
    if len(renk) == 1:
        return (renk[0],) * 3
    if len(renk) == 3:
        return renk
    if len(renk) == 4:
        c, m, y, k = renk
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def _renk_sinifi(rgb) -> str:
    if not rgb:
        return "notr"
    r, g, b = rgb
    if max(rgb) - min(rgb) < 0.18:      # siyah / gri tonlari
        return "notr"
    if r > g + 0.2 and r > b + 0.15:
        return "olumsuz"
    if g > r + 0.12 and g >= b - 0.05:
        return "olumlu"
    return "notr"


def _dolgulu_mu(rect) -> bool:
    if not rect.get("fill"):
        return False
    rgb = _rgb(rect.get("non_stroking_color"))
    return bool(rgb) and min(rgb) < 0.97   # beyaz olmayan dolgu


def _parcalara_ayir(kelimeler: list, bosluk: float = 22) -> list[_Parca]:
    """Ayni satirdaki kelimeleri, aralarindaki genis bosluga gore parcalara boler."""
    satirlar: list[list] = []
    for k in sorted(kelimeler, key=lambda k: (round(k["top"]), k["x0"])):
        if satirlar and abs(satirlar[-1][0]["top"] - k["top"]) < 3:
            satirlar[-1].append(k)
        else:
            satirlar.append([k])

    parcalar = []
    for satir in satirlar:
        satir.sort(key=lambda k: k["x0"])
        grup = [satir[0]]
        for k in satir[1:]:
            if k["x0"] - grup[-1]["x1"] > bosluk:
                parcalar.append(_grup_parca(grup))
                grup = [k]
            else:
                grup.append(k)
        parcalar.append(_grup_parca(grup))
    return parcalar


def _grup_parca(grup) -> _Parca:
    renkli = [_rgb(k.get("non_stroking_color")) for k in grup]
    renk = next((r for r in renkli if _renk_sinifi(r) != "notr"), renkli[0] if renkli else None)
    return _Parca(
        metin=" ".join(k["text"] for k in grup).strip(),
        x0=min(k["x0"] for k in grup), x1=max(k["x1"] for k in grup),
        top=min(k["top"] for k in grup), bottom=max(k["bottom"] for k in grup),
        kalin=all("bold" in (k.get("fontname") or "").lower() for k in grup),
        renk=renk,
    )


def _etiket_birim(metin: str) -> tuple[str, str]:
    metin = re.sub(r"\s+", " ", metin).strip()
    m = re.search(r"\(([^()]{1,15})\)\s*$", metin)
    if m and m.start() > 0:
        return metin[:m.start()].strip(), m.group(1).strip()
    return metin, ""


# --------------------------------------------------------------- kart bulma
def _kart_bolgeleri(sayfa) -> list[tuple]:
    """(x0, top, x1, bottom, baslik_bandi | None) listesi."""
    rects = sayfa.rects
    bantlar = [r for r in rects if r["height"] < 45 and r["width"] > 90 and _dolgulu_mu(r)]
    cerceveler = [r for r in rects if r["height"] > 120 and r["width"] > 90]

    bolgeler = []
    for c in cerceveler:
        # Ic ice cerceveleri ele (en distakini tut)
        if any(d is not c and d["x0"] <= c["x0"] + 1 and d["x1"] >= c["x1"] - 1
               and d["top"] <= c["top"] + 1 and d["bottom"] >= c["bottom"] - 1
               and (d["width"] * d["height"]) > (c["width"] * c["height"]) for d in cerceveler):
            continue
        bant = next((b for b in bantlar if abs(b["top"] - c["top"]) < 8
                     and b["x0"] >= c["x0"] - 3 and b["x1"] <= c["x1"] + 3), None)
        bolgeler.append((c["x0"], c["top"], c["x1"], c["bottom"], bant))

    if not bolgeler:
        # Cerceve cizgi olarak cizilmis olabilir: baslik bandindan asagiya dogru bolge
        for b in sorted(bantlar, key=lambda r: r["top"]):
            alt = min([o["top"] for o in bantlar if o["top"] > b["bottom"] + 20
                       and o["x0"] < b["x1"] and o["x1"] > b["x0"]] or [sayfa.height])
            bolgeler.append((b["x0"], b["top"], b["x1"], alt, b))
    return sorted(bolgeler, key=lambda r: (round(r[1] / 50), r[0]))


def _karti_oku(kelimeler, bolge) -> Kart | None:
    x0, top, x1, bottom, bant = bolge
    icerde = [k for k in kelimeler
              if x0 - 1 <= (k["x0"] + k["x1"]) / 2 <= x1 + 1 and top - 1 <= k["top"] <= bottom + 1]
    if not icerde:
        return None

    if bant:
        baslik_k = [k for k in icerde if bant["top"] - 1 <= k["top"] <= bant["bottom"] + 1]
        govde = [k for k in icerde if k not in baslik_k]
        baslik = " ".join(k["text"] for k in sorted(baslik_k, key=lambda k: k["x0"]))
    else:
        govde, baslik = icerde, ""

    parcalar = _parcalara_ayir(govde)
    degerler = [p for p in parcalar if DEGER.match(p.metin)]
    if len(degerler) < 2:
        return None
    kullanilan = set(id(p) for p in degerler)

    # Her degerin etiketi: hemen ustundeki, yatayda hizali metin satirlari
    metrikler = []
    for d in sorted(degerler, key=lambda p: (round(p.top), p.x0)):
        ustler = [p for p in parcalar if id(p) not in kullanilan and not DEGER.match(p.metin)
                  and p.bottom <= d.top + 2 and p.top >= d.top - 55
                  and (abs(p.xc - d.xc) < 55 or p.x0 - 5 <= d.xc <= p.x1 + 5)]
        # Arada baska bir deger varsa o etiket ona aittir
        ustler = [p for p in ustler if not any(
            id(o) != id(d) and o.top > p.bottom - 1 and o.bottom < d.top + 1
            and abs(o.xc - d.xc) < 55 for o in degerler)]
        ustler.sort(key=lambda p: p.top)
        for p in ustler:
            kullanilan.add(id(p))
        etiket, birim = _etiket_birim(" ".join(p.metin for p in ustler))

        ham = d.metin
        yon = "asagi" if set(ham) & OK_ASAGI else "yukari" if set(ham) & OK_YUKARI else ""
        deger = re.sub(r"[▲▼△▽↑↓]", "", ham).replace("−", "-").strip()
        renk = _renk_sinifi(d.renk)
        if not yon and renk != "notr":       # ok sembol fontuyla cizilmisse isaretten tahmin et
            yon = "asagi" if deger.startswith("-") else "yukari"

        ayni_satir = [o for o in degerler if abs(o.top - d.top) < 4]
        merkez = (x0 + x1) / 2
        one_cikan = len(ayni_satir) == 1 and abs(d.xc - merkez) < (x1 - x0) * 0.15

        metrikler.append(Metrik(etiket=etiket or "Değer", birim=birim, deger=deger,
                                renk=renk, yon=yon, one_cikan=one_cikan))
        metrikler[-1]._parca = d  # alt etiket eslestirmesi icin

    # Alt etiket: degerin hemen altindaki kisa metin (orn. "Randıman Etkisi")
    for m in metrikler:
        d = m._parca
        alt = [p for p in parcalar if id(p) not in kullanilan and not DEGER.match(p.metin)
               and 0 <= p.top - d.bottom < 30 and abs(p.xc - d.xc) < 60 and len(p.metin) < 40]
        if alt:
            m.alt_etiket = alt[0].metin
            kullanilan.add(id(alt[0]))
        del m._parca

    # Geriye kalan metin = yorum
    kalan = sorted((p for p in parcalar if id(p) not in kullanilan), key=lambda p: (p.top, p.x0))
    yorum = re.sub(r"\s+", " ", " ".join(p.metin for p in kalan)).strip()
    yorum = re.sub(r"(\w)- (\w)", r"\1\2", yorum)   # satir sonu tirelemesi

    return Kart(baslik=baslik.strip(), metrikler=metrikler, yorum=yorum)


def sayfa_duzeni(veri: bytes, sira: int) -> SayfaDuzeni | None:
    """sira: 0'dan baslar. Kart bulunamazsa None."""
    import pdfplumber

    with pdfplumber.open(BytesIO(veri)) as pdf:
        sayfa = pdf.pages[sira]
        kelimeler = sayfa.extract_words(extra_attrs=["fontname", "size", "non_stroking_color"])
        bolgeler = _kart_bolgeleri(sayfa)
        kartlar = [k for k in (_karti_oku(kelimeler, b) for b in bolgeler) if k]
        if not kartlar:
            return None

        # Ust baslik: kartlarin disinda, ilk kartin ustundeki en belirgin satir
        ilk_top = min(b[1] for b in bolgeler)
        disarida = [k for k in kelimeler if k["bottom"] < ilk_top - 2 and not any(
            b[0] - 1 <= (k["x0"] + k["x1"]) / 2 <= b[2] + 1 and b[1] - 1 <= k["top"] <= b[3] + 1
            for b in bolgeler)]
        ust = ""
        if disarida:
            parcalar = _parcalara_ayir(disarida, bosluk=40)
            parcalar.sort(key=lambda p: (not p.kalin, p.top))
            ust = parcalar[0].metin
        return SayfaDuzeni(ust_baslik=ust, kartlar=kartlar[:3])
