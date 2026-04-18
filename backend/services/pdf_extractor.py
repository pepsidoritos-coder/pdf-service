"""
Extrator de texto de documentos PDF usando PyMuPDF.
"""
import fitz
from backend.config import logger


def extract_text(pdf_bytes: bytes) -> dict:
    """
    Extrai texto e metadados de um PDF.

    Args:
        pdf_bytes: conteúdo binário do PDF

    Returns:
        dict com: raw_text, num_pages, metadata
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages.append({
            "page_number": i + 1,
            "text": text,
            "char_count": len(text)
        })

    raw_text = "\n".join([p["text"] for p in pages])
    num_pages = len(doc)
    non_empty_pages = sum(1 for p in pages if (p.get("char_count") or 0) > 20)
    avg_chars_per_page = int(len(raw_text) / max(num_pages, 1))
    low_text_density = avg_chars_per_page < 120 and non_empty_pages <= max(1, int(num_pages * 0.35))

    # Metadados do PDF (título, autor, etc.)
    meta = doc.metadata or {}
    pdf_metadata = {
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "creator": meta.get("creator", ""),
        "producer": meta.get("producer", ""),
        "creation_date": meta.get("creationDate", ""),
    }
    # Remove campos vazios
    pdf_metadata = {k: v for k, v in pdf_metadata.items() if v}

    doc.close()

    logger.info(f"📄 Extraído: {len(raw_text)} chars | {num_pages} páginas")

    return {
        "raw_text": raw_text,
        "num_pages": num_pages,
        "pages": pages,
        "pdf_metadata": pdf_metadata,
        "extraction_quality": {
            "avg_chars_per_page": avg_chars_per_page,
            "non_empty_pages": non_empty_pages,
            "low_text_density": low_text_density,
        },
    }
