"""LLM'den gelen SSML icerigini bolumlere ayirir.

Ornek girdi:
    <prosody rate="-04%">Baslik.<break time="300ms"/>Birinci bolum. <prosody rate="-10%">Vurgu.</prosody>
    <break time="300ms"/>Ikinci bolum.</prosody>

Her <break> bir bolum siniri kabul edilir. Ic ice <prosody> etiketleri her bolumde
yeniden kurulur, boylece her bolum tek basina gecerli bir SSML parcasi olur.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

SSML_NS = "{http://www.w3.org/2001/10/synthesis}"


@dataclass
class Bolum:
    ssml: str                 # TTS'e gidecek parca (<speak> zarfi olmadan)
    metin: str                # Etiketsiz duz metin (slayt ve altyazi icin)
    ara_sure: str = "300ms"   # Bolum sonundaki duraklama
    cumleler: list = field(default_factory=list)  # altyazi parcalari
    baslik: str = ""          # slayt basligi (bolumun ilk tam cumlesi)


def ampersand_duzelt(metin: str) -> str:
    """Tek basina '&' isaretleri XML'i bozar (orn. 'Ar&Ge')."""
    return re.sub(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", metin)


def _etiket(el) -> str:
    return el.tag.replace(SSML_NS, "")


def _parcalara_ayir(icerik: str):
    """SSML'i [("metin", yazi, prosody_yigini) | ("break", sure)] listesine cevirir."""
    icerik = ampersand_duzelt(icerik.strip())

    # Tam <speak> belgesi geldiyse <voice> icini al
    if icerik.startswith("<speak"):
        kok = ET.fromstring(icerik)
        ses = next((e for e in kok.iter() if _etiket(e) == "voice"), kok)
        kok = ses
    else:
        kok = ET.fromstring(f"<kok>{icerik}</kok>")

    parcalar = []

    def gez(el, yigin):
        if el.text:
            parcalar.append(("metin", el.text, yigin))
        for cocuk in el:
            ad = _etiket(cocuk)
            if ad == "break":
                parcalar.append(("break", cocuk.get("time", "300ms")))
            elif ad == "prosody":
                gez(cocuk, yigin + [dict(cocuk.attrib)])
            elif ad in ("lexicon",):
                pass
            else:
                # Taninmayan etiketlerin sadece metnini al
                gez(cocuk, yigin)
            if cocuk.tail:
                parcalar.append(("metin", cocuk.tail, yigin))

    gez(kok, [])
    return parcalar


def _prosody_sar(yazi: str, yigin: list) -> str:
    sonuc = escape(yazi)
    for nitelik in reversed(yigin):
        attr = " ".join(f"{k}={quoteattr(v)}" for k, v in nitelik.items())
        sonuc = f"<prosody {attr}>{sonuc}</prosody>"
    return sonuc


def _duzelt_bosluk(metin: str) -> str:
    return re.sub(r"\s+", " ", metin).strip()


def altyazi_temizle(metin: str) -> str:
    """Altyazidan noktalama isaretlerini kaldirir.
    Kelime ici kesme isareti (Türkiye'nin) ve sayi ici ayraclar (97.207, 4,02) korunur."""
    metin = re.sub(r"(?<=\d)([.,])(?=\d)", lambda m: "\x00" if m.group(1) == "." else "\x01", metin)
    metin = re.sub(r"[,.;:!?…\"“”«»()\[\]{}<>=*#|_~^]", " ", metin)
    metin = re.sub(r"\s*[-–—/]\s*", " ", metin)        # tire ve egik cizgi -> bosluk
    metin = re.sub(r"(^|\s)['‘’]|['‘’](\s|$)", " ", metin)  # kelime disindaki tirnaklar
    metin = metin.replace("\x00", ".").replace("\x01", ",")
    return re.sub(r"\s+", " ", metin).strip()


def _tam_cumleler(metin: str) -> list[str]:
    # "1. Gösterge" veya "15.10.2026" gibi rakamdan sonraki noktada bolme
    return [c.strip() for c in re.split(r"(?<=[^\d\s][.!?])\s+", metin) if c.strip()]


def cumlelere_bol(metin: str, azami: int = 110) -> list[str]:
    """Altyazi icin metni cumlelere boler; uzun cumleleri esit uzunlukta parcalara ayirir."""
    sonuc = []
    for c in _tam_cumleler(metin):
        if len(c) <= azami:
            sonuc.append(c)
            continue
        kelimeler = c.split(" ")
        parca_sayisi = -(-len(c) // azami)          # yukari yuvarla
        hedef = len(c) / parca_sayisi
        parca = ""
        for kelime in kelimeler:
            aday = f"{parca} {kelime}".strip()
            if len(aday) > hedef and parca and len(sonuc) < 10_000:
                sonuc.append(parca)
                parca = kelime
            else:
                parca = aday
        if parca:
            # Tek kelimelik kuyruk kalmasin: onceki parcaya ekle
            if " " not in parca and sonuc and len(sonuc[-1]) + len(parca) < azami * 1.3:
                sonuc[-1] = f"{sonuc[-1]} {parca}"
            else:
                sonuc.append(parca)
    temiz = [t for t in (altyazi_temizle(x) for x in sonuc) if t]
    # Cok kisa parcalar (orn. tek basina "1") ekranda bir an gorunup kaybolmasin
    birlesik = []
    for t in temiz:
        if birlesik and (len(birlesik[-1]) <= 3 or len(t) <= 3):
            birlesik[-1] = f"{birlesik[-1]} {t}"
        else:
            birlesik.append(t)
    return birlesik


def bolumlere_ayir(icerik: str) -> list[Bolum]:
    try:
        parcalar = _parcalara_ayir(icerik)
    except ET.ParseError as e:
        raise ValueError(
            f"SSML okunamadi: {e}. Kapanmamis bir <prosody> etiketi olabilir."
        ) from e

    bolumler, ssml, duz = [], [], []

    def kapat(ara="300ms"):
        metin = _duzelt_bosluk("".join(duz))
        if metin:
            bolumler.append(
                Bolum(ssml="".join(ssml).strip(), metin=metin, ara_sure=ara,
                      cumleler=cumlelere_bol(metin),
                      baslik=(_tam_cumleler(metin) or [metin])[0].rstrip(".").strip())
            )
        ssml.clear()
        duz.clear()

    for p in parcalar:
        if p[0] == "break":
            kapat(p[1])
        else:
            _, yazi, yigin = p
            if yazi.strip():
                ssml.append(_prosody_sar(yazi, yigin))
            duz.append(yazi)
    kapat()
    return bolumler


def etiketsiz(icerik: str) -> str:
    """Onizleme icin SSML etiketlerini kaldirir."""
    duz = re.sub(r"<break[^>]*/>", "\n", icerik)
    return re.sub(r"<[^>]+>", "", duz).strip()
