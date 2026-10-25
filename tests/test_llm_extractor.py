import json

import pytest

from src.llm_extractor import extract_llm, parse_response, postprocess
from src.perturb import relabel, reorder
from src.regex_extractor import extract
from src.schema import CAMPOS, CAMPOS_LINEA

TEXT = """Número de factura: PR-1                 Pedido: PED-1
Fecha de emisión: 15/09/2026
EMISOR                     CLIENTE
Papelería Demo             Centro Demo
TOTAL                      243,79 EUR
"""


def response(**campos) -> dict:
    return {"campos": {k: campos.get(k) for k in CAMPOS}, "lineas": []}


class FakeBackend:
    """Devuelve respuestas predefinidas, una por llamada."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def generate(self, messages):
        self.calls.append(messages)
        return self.answers.pop(0), {"prompt_tokens": 1, "completion_tokens": 1}


# ---------------------------------------------------------------- formato

def test_parse_rechaza_claves_que_faltan():
    with pytest.raises(ValueError):
        parse_response(json.dumps({"campos": {"total": "1"}, "lineas": []}))


def test_parse_acepta_bloque_de_codigo():
    assert parse_response("```json\n" + json.dumps(response()) + "\n```")["lineas"] == []


def test_reintento_tras_json_invalido_y_traza_guardada():
    backend = FakeBackend("no es json", json.dumps(response(total="243,79 EUR")))
    out = extract_llm(TEXT, backend)
    assert out["campos"]["total"] == "243.79"
    intentos = out["traza"]["intentos"]
    assert [a["valido"] for a in intentos] == [False, True]
    assert "no es válida" in backend.calls[1][-1]["content"]          # el reintento explica el error
    assert TEXT in out["traza"]["mensajes"][1]["content"]              # prompt completo guardado


def test_sin_json_valido_todo_null_y_error():
    out = extract_llm(TEXT, FakeBackend("x", "y"))
    assert out["error"] and all(v is None for v in out["campos"].values())


# ---------------------------------------------------------------- normalización y evidencia

def test_normaliza_con_las_mismas_reglas_que_la_regex():
    res, _ = postprocess(response(fecha_emision="15/09/2026", total="243,79 EUR"), TEXT)
    assert res["campos"]["fecha_emision"] == "2026-09-15" and res["campos"]["total"] == "243.79"


def test_valor_sin_evidencia_en_el_texto_se_descarta():
    data = response(emisor_nombre="Papelería Demo", cliente_email="compras@centro.example")  # el email no está
    res, descartados = postprocess(data, TEXT)
    assert res["campos"]["emisor_nombre"] == "Papelería Demo"
    assert res["campos"]["cliente_email"] is None
    assert descartados == {"cliente_email": "compras@centro.example"}


def test_lineas_se_verifican_celda_a_celda():
    line = dict.fromkeys(CAMPOS_LINEA, None) | {"referencia": "PED-1", "importe": "99,99"}
    res, descartados = postprocess({"campos": response()["campos"], "lineas": [line]}, TEXT)
    assert res["lineas"][0]["referencia"] == "PED-1" and res["lineas"][0]["importe"] is None
    assert "lineas[0].importe" in descartados


# ---------------------------------------------------------------- variantes

def test_variante_etiquetas_rompe_la_regex_donde_no_conoce_el_sinonimo():
    c = extract(relabel(TEXT))["campos"]
    assert c["numero_factura"] is None                  # "Nº Fra." no está en la regex
    assert c["numero_pedido"] == "PED-1"                # "Su pedido" sí
    assert c["total"] == "243.79"                       # "Importe total" sí


def test_variante_orden_pone_una_celda_por_linea():
    assert reorder(TEXT).splitlines()[:3] == ["Número de factura: PR-1", "Pedido: PED-1", "Fecha de emisión: 15/09/2026"]
    assert extract(reorder(TEXT))["campos"]["emisor_nombre"] is None


def test_formato_invalido_se_descarta_aunque_este_en_el_texto():
    text = TEXT + "Email: ventasOemisor04.example\n"
    res, _ = postprocess(response(cliente_email="ventasOemisor04.example", moneda="Pedido"), text)
    assert res["campos"]["cliente_email"] is None and res["campos"]["moneda"] is None


def test_unidad_copiada_de_la_cabecera_no_invalida_el_numero():
    """El modelo copia 'EUR' de la cabecera 'Precio EUR'; en la fila solo está '8,50'."""
    line = dict.fromkeys(CAMPOS_LINEA, None) | {"precio_unitario": "8,50 EUR", "iva_pct": "21 %"}
    text = "MAT-1   Cuadernos   5   8,50   0   21   42,50\n"
    res, descartados = postprocess({"campos": response()["campos"], "lineas": [line]}, text)
    assert res["lineas"][0]["precio_unitario"] == "8.50" and res["lineas"][0]["iva_pct"] == "21"
    assert descartados == {}
