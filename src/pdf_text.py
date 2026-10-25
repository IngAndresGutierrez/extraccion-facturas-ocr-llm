"""Lectura del texto seleccionable de un PDF con PyMuPDF (Parte 1, sin OCR)."""
import pymupdf

PAGE_SEPARATOR = "\n\n===== PÁGINA {n} =====\n\n"
# Por debajo de este número de caracteres consideramos que la página no tiene capa de texto.
MIN_CHARS_TEXT_LAYER = 20


def read_pages(pdf: str | bytes) -> list[str]:
    """Texto de cada página en orden de lectura de PyMuPDF (sort=True: arriba-abajo, izquierda-derecha)."""
    doc = pymupdf.open(stream=pdf, filetype="pdf") if isinstance(pdf, bytes) else pymupdf.open(pdf)
    with doc:
        return [page.get_text("text", sort=True) for page in doc]


def join_pages(pages: list[str]) -> str:
    """Une las páginas conservando su separación (útil para revisar errores)."""
    return "".join(PAGE_SEPARATOR.format(n=i) + t for i, t in enumerate(pages, 1)).lstrip()


def has_text_layer(pages: list[str]) -> bool:
    return sum(len(p.strip()) for p in pages) >= MIN_CHARS_TEXT_LAYER
