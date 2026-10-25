from pathlib import Path

import pytest

from src import normalize as norm
from src.pdf_text import has_text_layer, join_pages, read_pages
from src.regex_extractor import extract

PDFS = Path(__file__).resolve().parent.parent / "pdfs"


# ---------------------------------------------------------------- normalización

@pytest.mark.parametrize("raw,expected", [
    ("1.234,50", "1234.50"), ("127,33", "127.33"), ("0,00", "0.00"), ("21", "21"),
    ("12.34", None), ("abc", None), (None, None),
])
def test_amount(raw, expected):
    assert norm.amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("01/09/2026", "2026-09-01"), ("1-9-2026", "2026-09-01"), ("31/02/2026", None), ("01/09/26", None),
])
def test_date_iso(raw, expected):
    assert norm.date_iso(raw) == expected


def test_iban_quita_espacios():
    assert norm.iban("ES00 0000 0000 0000 0000 0001") == "ES0000000000000000000001"


# ---------------------------------------------------------------- PDFs reales (valores leídos del documento)

EXPECTED = {
    "Factura_01_texto.pdf": {"numero_factura": "PR-2026-001", "fecha_emision": "2026-09-01",
                             "numero_pedido": "PED-2026-0101", "emisor_nombre": "Papelería Aula Demo",
                             "cliente_id_fiscal": "DEMO-C-001", "forma_pago": "Transferencia",
                             "base_imponible": "127.33", "iva_importe": "26.74", "total": "154.07"},
    "Factura_02_texto.pdf": {"numero_factura": "PR-2026-002", "fecha_vencimiento": "2026-10-04",
                             "cliente_nombre": "Academia Horizonte Ficticia", "forma_pago": "Tarjeta",
                             "iban": "ES0000000000000000000002", "total": "150.03"},
    "Factura_03_texto.pdf": {"numero_factura": "PR-2026-003", "emisor_nombre": "Material Escolar Demo",
                             "cliente_email": "compras@cliente03.example", "base_imponible": "172.00",
                             "iva_importe": "36.12", "total": "208.12"},
}


@pytest.mark.parametrize("name", EXPECTED)
def test_pdf_texto(name):
    pages = read_pages(str(PDFS / name))
    out = extract(join_pages(pages))
    for field, value in EXPECTED[name].items():
        assert out["campos"][field] == value, field
    assert all(v is not None for v in out["campos"].values())
    assert len(out["lineas"]) == 5


def test_lineas_factura_02():
    out = extract(join_pages(read_pages(str(PDFS / "Factura_02_texto.pdf"))))
    assert out["lineas"][1] == {"referencia": "MAT-2002", "descripcion": "Rotuladores de colores",
                                "cantidad": "3", "precio_unitario": "7.40", "descuento_pct": "5",
                                "iva_pct": "21", "importe": "21.09"}


@pytest.mark.parametrize("name", ["Factura_04_imagen.pdf", "Factura_05_imagen.pdf"])
def test_pdf_imagen_sin_texto(name):
    assert not has_text_layer(read_pages(str(PDFS / name)))


# ---------------------------------------------------------------- variantes y casos límite

def test_variantes_de_etiqueta():
    text = "N.º factura: F/2025-77\nFecha factura: 3.1.2025\nNúmero de pedido: P-9\nTotal a pagar: 1.234,50 EUR\n"
    c = extract(text)["campos"]
    assert c["numero_factura"] == "F/2025-77"
    assert c["fecha_emision"] == "2025-01-03"
    assert c["numero_pedido"] == "P-9"
    assert c["total"] == "1234.50"


def test_fecha_de_pedido_no_es_numero_de_pedido():
    assert extract("Fecha de pedido: 30/08/2026\n")["campos"]["numero_pedido"] is None


def test_subtotal_no_es_total():
    assert extract("Subtotal sin descuentos   129,50 EUR\n")["campos"]["total"] is None


def test_valores_distintos_son_ambiguos():
    assert extract("TOTAL 10,00 EUR\nTOTAL 12,00 EUR\n")["campos"]["total"] is None


def test_cero_no_es_null():
    assert extract("Base imponible: 0,00 EUR\n")["campos"]["base_imponible"] == "0.00"


def test_campo_ausente_es_null():
    out = extract("FACTURA\nSin datos\n")
    assert all(v is None for v in out["campos"].values())
    assert out["lineas"] == []


def test_fila_de_una_sola_columna_no_se_atribuye():
    text = ("EMISOR      CLIENTE\nEmisor SA      Cliente SL\n"
            "ID fiscal: E-1\n"  # no sabemos de qué columna es
            "Referencia  Descripción\n")
    c = extract(text)["campos"]
    assert c["emisor_nombre"] == "Emisor SA"
    assert c["emisor_id_fiscal"] is None and c["cliente_id_fiscal"] is None
