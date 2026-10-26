"""PDF'i sayfa sayfa okur: her sayfanin metni ve goruntusu."""
from io import BytesIO

from PIL import Image


def sayfa_metinleri(veri: bytes) -> list[str]:
    import pdfplumber

    with pdfplumber.open(BytesIO(veri)) as pdf:
        return [(s.extract_text() or "").strip() for s in pdf.pages]


def sayfa_gorseli(veri: bytes, sira: int, dpi: int = 150) -> Image.Image:
    """sira: 0'dan baslar."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(veri)
    try:
        sayfa = pdf[sira]
        return sayfa.render(scale=dpi / 72).to_pil().convert("RGB")
    finally:
        pdf.close()


def sayfa_sayisi(veri: bytes) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(veri)
    try:
        return len(pdf)
    finally:
        pdf.close()
