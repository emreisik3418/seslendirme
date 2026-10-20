"""Word (.docx) ve PDF dosyalarindan duz metin cikarir."""
from io import BytesIO
from pathlib import Path


def word_oku(veri: bytes) -> str:
    from docx import Document

    belge = Document(BytesIO(veri))
    satirlar = [p.text.strip() for p in belge.paragraphs if p.text.strip()]

    # Tablolardaki metni de al (satir satir, hucreler " | " ile)
    for tablo in belge.tables:
        for satir in tablo.rows:
            hucreler = [h.text.strip() for h in satir.cells if h.text.strip()]
            if hucreler:
                satirlar.append(" | ".join(hucreler))

    return "\n".join(satirlar)


def pdf_oku(veri: bytes) -> str:
    import pdfplumber

    sayfalar = []
    with pdfplumber.open(BytesIO(veri)) as pdf:
        for sayfa in pdf.pages:
            metin = sayfa.extract_text() or ""
            if metin.strip():
                sayfalar.append(metin.strip())
    return "\n\n".join(sayfalar)


def metin_cikar(dosya_adi: str, veri: bytes) -> str:
    uzanti = Path(dosya_adi).suffix.lower()
    if uzanti == ".docx":
        return word_oku(veri)
    if uzanti == ".pdf":
        return pdf_oku(veri)
    if uzanti == ".txt":
        return veri.decode("utf-8", errors="replace")
    raise ValueError(f"Desteklenmeyen dosya turu: {uzanti} (.docx, .pdf veya .txt olmali)")
