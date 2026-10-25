import re
from pathlib import Path

import pytest

from src import ocr, render
from src.ocr import Word, layout_text
from src.pdf_text import join_pages, read_pages
from src.regex_extractor import extract

PDFS = Path(__file__).resolve().parent.parent / "pdfs"


def w(text, x0, y0, char_w=10, h=20):
    return Word(text, x0, y0, x0 + char_w * len(text), y0 + h, 95.0)


# ---------------------------------------------------------------- reconstrucción de disposición

def test_palabras_juntas_un_espacio_columnas_dos_o_mas():
    words = [w("ID", 0, 100), w("fiscal:", 30, 102), w("E-1", 110, 99),
             w("ID", 400, 101), w("fiscal:", 430, 100), w("C-1", 510, 100)]
    line = layout_text(words).rstrip("\n")
    assert re.split(r"\s{2,}", line) == ["ID fiscal: E-1", "ID fiscal: C-1"]


def test_lineas_ordenadas_por_altura_aunque_lleguen_desordenadas():
    words = [w("abajo", 0, 200), w("derecha", 400, 50), w("arriba", 0, 52)]
    lines = layout_text(words).splitlines()
    assert lines[0].split() == ["arriba", "derecha"] and lines[1] == "abajo"


def test_texto_reconstruido_alimenta_las_reglas_de_la_parte_1():
    words = [w("EMISOR", 0, 0), w("CLIENTE", 400, 0),
             w("Emisor", 0, 40), w("SA", 70, 40), w("Cliente", 400, 40), w("SL", 480, 40),
             w("Referencia", 0, 80), w("Descripción", 120, 80)]
    c = extract(layout_text(words))["campos"]
    assert (c["emisor_nombre"], c["cliente_nombre"]) == ("Emisor SA", "Cliente SL")


def test_preprocesado_binariza():
    from PIL import Image
    img = Image.new("RGB", (2, 1)); img.putpixel((0, 0), (120, 130, 150)); img.putpixel((1, 0), (240, 240, 240))
    assert list(ocr.preprocess(img, "binarize").getdata()) == [0, 255]


# ---------------------------------------------------------------- integración con Tesseract

EXPECTED = {  # leído de la imagen del documento
    "Factura_04_imagen.pdf": {"numero_factura": "PR-2026-004", "fecha_emision": "2026-09-15",
                              "emisor_nombre": "Papelería Taller Demo", "forma_pago": "Domiciliación",
                              "iban": "ES0000000000000000000004", "total": "243.79"},
    "Factura_05_imagen.pdf": {"numero_factura": "PR-2026-005", "cliente_nombre": "Instituto de Prácticas Ejemplo",
                              "iban": "ES0000000000000000000005", "base_imponible": "228.63", "total": "276.64"},
}


@pytest.mark.parametrize("name", EXPECTED)
def test_ocr_tesseract_pdf_imagen(name):
    engine = ocr.get_engine("tesseract")
    img = ocr.preprocess(render.render_pages(str(PDFS / name))[0], "binarize")
    out = extract(join_pages([layout_text(engine.read(img))]))
    for field, value in EXPECTED[name].items():
        assert out["campos"][field] == value, field
    assert len(out["lineas"]) == 5


def test_ocr_y_texto_directo_coinciden_en_misma_plantilla():
    """Control: el OCR de un PDF con texto debe dar los mismos campos que la lectura directa."""
    path = str(PDFS / "Factura_01_texto.pdf")
    direct = extract(join_pages(read_pages(path)))
    img = ocr.preprocess(render.render_pages(path)[0], "binarize")
    via_ocr = extract(join_pages([layout_text(ocr.get_engine("tesseract").read(img))]))
    diff = {k for k in direct["campos"] if direct["campos"][k] != via_ocr["campos"][k]}
    assert diff <= {"cliente_email"}  # '@' es la única confusión conocida de Tesseract
    assert via_ocr["lineas"] == direct["lineas"]
