"""OCR de imágenes y reconstrucción del texto con disposición.

Cada motor devuelve palabras con su caja (x0, y0, x1, y1) y confianza. layout_text() las convierte en
el mismo formato que PyMuPDF con sort=True (una línea visual por línea, columnas separadas por 2+
espacios), para que las reglas regex de la Parte 1 se reutilicen sin cambios.
"""
from dataclasses import asdict, dataclass
from statistics import median

from PIL import Image, ImageOps


# ---------------------------------------------------------------- preprocesado

def preprocess(image: Image.Image, mode: str = "binarize", threshold: int = 170) -> Image.Image:
    """'none': imagen tal cual. 'gray': escala de grises. 'binarize': grises + umbral fijo.
    El texto de las facturas es gris azulado sobre blanco; con umbral 170 Tesseract deja de
    confundir '0' con 'O' en el IBAN (ver README)."""
    if mode == "none":
        return image
    gray = ImageOps.grayscale(image)
    if mode == "gray":
        return gray
    if mode == "binarize":
        return gray.point(lambda p: 255 if p > threshold else 0)
    raise ValueError(f"Preprocesado desconocido: {mode}")


@dataclass
class Word:
    text: str
    x0: int
    y0: int
    x1: int
    y1: int
    conf: float


# ---------------------------------------------------------------- motores

class TesseractOCR:
    name = "tesseract"

    # psm 3 (segmentación automática): psm 11 perdía los dígitos aislados de la tabla (cantidades, Dto.).
    def __init__(self, lang: str = "spa", psm: int = 3, oem: int = 1):
        import pytesseract
        self._tess = pytesseract
        self.lang, self.psm, self.oem = lang, psm, oem

    @property
    def config(self) -> dict:
        return {"engine": "tesseract", "version": str(self._tess.get_tesseract_version()),
                "lang": self.lang, "psm": self.psm, "oem": self.oem}

    def read(self, image: Image.Image) -> list[Word]:
        data = self._tess.image_to_data(image, lang=self.lang, config=f"--oem {self.oem} --psm {self.psm}",
                                        output_type=self._tess.Output.DICT)
        words = []
        for i, txt in enumerate(data["text"]):
            if txt.strip() and float(data["conf"][i]) >= 0:
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                words.append(Word(txt.strip(), x, y, x + w, y + h, float(data["conf"][i])))
        return words


ENGINES = {"tesseract": TesseractOCR}


def get_engine(name: str, **kwargs):
    return ENGINES[name](**kwargs)


# ---------------------------------------------------------------- disposición

def group_lines(words: list[Word]) -> list[list[Word]]:
    """Agrupa palabras en líneas visuales por solapamiento vertical, independientemente de la columna."""
    if not words:
        return []
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        cy, h = (w.y0 + w.y1) / 2, w.y1 - w.y0
        if lines:
            last = lines[-1]
            ly = median((x.y0 + x.y1) / 2 for x in last)
            lh = median(x.y1 - x.y0 for x in last)
            if abs(cy - ly) <= 0.5 * max(h, lh):
                last.append(w)
                continue
        lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def layout_text(words: list[Word]) -> str:
    """Una línea por fila visual. Entre palabras, 1 espacio si están juntas y 2+ si el hueco
    indica otra columna (más de ~2 caracteres de ancho)."""
    if not words:
        return ""
    char_w = median((w.x1 - w.x0) / len(w.text) for w in words)
    out = []
    for line in group_lines(words):
        parts = [line[0].text]
        for prev, w in zip(line, line[1:]):
            gap = (w.x0 - prev.x1) / char_w
            parts.append(" " * max(2, round(gap)) if gap > 2 else " ")
            parts.append(w.text)
        out.append("".join(parts))
    return "\n".join(out) + "\n"


def words_to_json(words: list[Word]) -> list[dict]:
    return [asdict(w) for w in words]
