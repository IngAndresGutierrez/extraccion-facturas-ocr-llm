"""Renderizado de páginas PDF a imagen (entrada del OCR)."""
import io

import pymupdf
from PIL import Image

# Las facturas escaneadas contienen una imagen de 2067x2924 px en A4 (~250 DPI):
# renderizar a 250 DPI conserva la resolución original sin reescalar.
DEFAULT_DPI = 250


def render_pages(pdf: str | bytes, dpi: int = DEFAULT_DPI) -> list[Image.Image]:
    """Página completa (no solo las imágenes incrustadas), en orden, como imágenes RGB."""
    doc = pymupdf.open(stream=pdf, filetype="pdf") if isinstance(pdf, bytes) else pymupdf.open(pdf)
    with doc:
        return [Image.open(io.BytesIO(page.get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB")
                for page in doc]
