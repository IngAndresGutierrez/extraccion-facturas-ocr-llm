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


class EasyOCR:
    """PyTorch: detector CRAFT (craft_mlt_25k) + reconocedor CRNN 'latin_g2' (incluye á, é, í, ó, ú, ñ)."""
    name = "easyocr"

    def __init__(self, lang: str = "es"):
        import os
        import easyocr
        import torch
        self._version, self._torch = easyocr.__version__, torch.__version__
        self.lang = lang
        self.reader = easyocr.Reader([lang], gpu=False, verbose=False,
                                     model_storage_directory=os.path.join(os.environ.get("MODELS_DIR", "/models"), "easyocr"),
                                     download_enabled=False)

    @property
    def config(self) -> dict:
        return {"engine": "easyocr", "version": self._version, "torch": self._torch, "lang": self.lang,
                "detector": "craft_mlt_25k", "recognizer": "latin_g2"}

    def read(self, image: Image.Image) -> list[Word]:
        import numpy as np
        words = []
        for box, txt, conf in self.reader.readtext(np.array(image.convert("RGB")), detail=1, paragraph=False):
            if txt.strip():
                xs, ys = [p[0] for p in box], [p[1] for p in box]
                words.append(Word(txt.strip(), int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)),
                                  round(float(conf) * 100, 1)))
        return words


class DocTR:
    """PyTorch: detector FAST (fast_base) + reconocedor CRNN (crnn_vgg16_bn), modelos oficiales de docTR.
    Ojo: su vocabulario no incluye á, í, ó, ú ni ñ."""
    name = "doctr"

    def __init__(self, det_arch: str = "fast_base", reco_arch: str = "crnn_vgg16_bn"):
        import doctr
        import torch
        from doctr.models import ocr_predictor
        self._version, self._torch = doctr.__version__, torch.__version__
        self.det_arch, self.reco_arch = det_arch, reco_arch
        self.predictor = ocr_predictor(det_arch=det_arch, reco_arch=reco_arch, pretrained=True)

    @property
    def config(self) -> dict:
        return {"engine": "doctr", "version": self._version, "torch": self._torch,
                "detector": self.det_arch, "recognizer": self.reco_arch,
                "vocab": f"{len(self.predictor.reco_predictor.model.vocab)} caracteres (francés)"}

    def read(self, image: Image.Image) -> list[Word]:
        import numpy as np
        page = self.predictor([np.array(image.convert("RGB"))]).pages[0]
        w, h = image.size
        words = []
        for block in page.blocks:
            for line in block.lines:
                for wd in line.words:
                    (x0, y0), (x1, y1) = wd.geometry
                    if wd.value.strip():
                        words.append(Word(wd.value.strip(), int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h),
                                          round(float(wd.confidence) * 100, 1)))
        return words


ENGINES = {"tesseract": TesseractOCR, "easyocr": EasyOCR, "doctr": DocTR}


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
