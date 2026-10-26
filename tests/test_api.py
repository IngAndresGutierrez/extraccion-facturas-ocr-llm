import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import api, pipeline
from src.schema import CAMPOS

PDFS = Path(__file__).resolve().parent.parent / "pdfs"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "OUT", tmp_path)  # evidencias de los tests fuera de resultados/
    return TestClient(api.app)


def submit(client, name: str, method: str, content: bytes | None = None):
    data = content if content is not None else (PDFS / name).read_bytes()
    return client.post("/api/extract", files={"file": (name, data, "application/pdf")}, data={"method": method})


def wait(client, job_id: str, timeout: float = 30) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["estado"] in ("completado", "error", "cancelado"):
            return job
        time.sleep(0.1)
    raise TimeoutError(job)


def test_sirve_la_interfaz(client):
    assert "<form" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_texto_regex_pdf_con_texto(client):
    r = submit(client, "Factura_01_texto.pdf", "texto_regex")
    assert r.status_code == 202
    job = wait(client, r.json()["job_id"])
    assert job["estado"] == "completado"
    assert job["resultado"]["campos"]["total"] == "154.07"
    assert len(job["resultado"]["lineas"]) == 5
    d = client.get(f"/api/jobs/{job['id']}/descarga")
    assert "attachment" in d.headers["content-disposition"]
    assert d.json()["campos"]["numero_factura"] == "PR-2026-001"


def test_ocr_regex_pdf_escaneado_guarda_evidencias(client, tmp_path):
    job = wait(client, submit(client, "Factura_04_imagen.pdf", "ocr_regex").json()["job_id"])
    assert job["estado"] == "completado"
    assert job["resultado"]["campos"]["iban"] == "ES0000000000000000000004"
    files = {p.name for p in (tmp_path / job["id"]).iterdir()}
    assert {"texto_leido.txt", "ocr_original.json", "resultado.json", "pagina_1_binarize.png"} <= files


def test_texto_regex_en_pdf_escaneado_explica_el_error(client):
    job = wait(client, submit(client, "Factura_04_imagen.pdf", "texto_regex").json()["job_id"])
    assert job["estado"] == "error"
    assert "no tiene texto seleccionable" in job["mensaje"] and "OCR" in job["mensaje"]


def test_ocr_llm_con_backend_simulado(client, monkeypatch):
    class Fake:
        config = {"runtime": "fake"}

        def generate(self, messages):
            campos = dict.fromkeys(CAMPOS) | {"numero_factura": "PR-2026-004", "total": "243,79 EUR",
                                              "emisor_nombre": "Inventada SL"}  # no está en el texto
            return json.dumps({"campos": campos, "lineas": []}), {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setitem(pipeline._engines, "llm", Fake())
    job = wait(client, submit(client, "Factura_04_imagen.pdf", "ocr_llm").json()["job_id"])
    assert job["estado"] == "completado", job
    c = job["resultado"]["campos"]
    assert c["numero_factura"] == "PR-2026-004" and c["total"] == "243.79"
    assert c["emisor_nombre"] is None
    assert job["resultado"]["detalles"]["llm"]["descartados_sin_evidencia"] == {"emisor_nombre": "Inventada SL"}
    assert any("descartaron" in a for a in job["resultado"]["avisos"])


@pytest.mark.parametrize("name,content,method,status,msg", [
    ("notas.txt", b"hola", "texto_regex", 400, "no es un PDF"),
    ("vacio.pdf", b"", "texto_regex", 400, "vacío"),
    ("Factura_01_texto.pdf", None, "magia", 400, "Método desconocido"),
])
def test_errores_de_entrada(client, name, content, method, status, msg):
    r = submit(client, name, method, content)
    assert r.status_code == status and msg in r.json()["detail"]


def test_pdf_danado(client):
    job = wait(client, submit(client, "roto.pdf", "texto_regex", b"%PDF-1.7\nbasura").json()["job_id"])
    assert job["estado"] == "error" and "No se pudo abrir el PDF" in job["mensaje"]


def test_trabajo_inexistente(client):
    assert client.get("/api/jobs/nope").status_code == 404


@pytest.mark.parametrize("name,tiene_texto,sugerido", [
    ("Factura_01_texto.pdf", True, "texto_regex"),
    ("Factura_04_imagen.pdf", False, "ocr_regex"),
])
def test_analizar_sugiere_metodo(client, name, tiene_texto, sugerido):
    r = client.post("/api/analizar", files={"file": (name, (PDFS / name).read_bytes(), "application/pdf")})
    assert r.json() == {"paginas": 1, "tiene_texto": tiene_texto, "metodo_sugerido": sugerido}


def test_analizar_pdf_danado(client):
    r = client.post("/api/analizar", files={"file": ("roto.pdf", b"%PDF-1.7\nbasura", "application/pdf")})
    assert r.status_code == 400 and "No se pudo abrir el PDF" in r.json()["detail"]


def test_cancelar_en_proceso_y_en_cola(client, monkeypatch):
    soltar = threading.Event()

    def lento(pdf, method, filename, job_id, progress):
        progress("Etapa 1")
        soltar.wait(10)
        progress("Etapa 2")  # aquí se detiene si se canceló
        return {}

    monkeypatch.setattr(pipeline, "run", lento)
    primero = submit(client, "Factura_01_texto.pdf", "texto_regex").json()["job_id"]
    segundo = submit(client, "Factura_01_texto.pdf", "texto_regex").json()["job_id"]
    while client.get(f"/api/jobs/{primero}").json()["etapa"] != "Etapa 1":
        time.sleep(0.05)

    assert client.delete(f"/api/jobs/{segundo}").json() == {"estado": "cancelado"}
    assert client.delete(f"/api/jobs/{primero}").json() == {"estado": "procesando"}
    soltar.set()
    end = time.time() + 10
    while client.get(f"/api/jobs/{primero}").json()["estado"] != "cancelado" and time.time() < end:
        time.sleep(0.05)
    assert client.get(f"/api/jobs/{primero}").json()["estado"] == "cancelado"
    assert client.delete(f"/api/jobs/{primero}").status_code == 409


def test_estimado_usa_el_historial(client):
    job = wait(client, submit(client, "Factura_01_texto.pdf", "texto_regex").json()["job_id"])
    assert client.get(f"/api/jobs/{job['id']}").json()["estimado_s"] < api.ESTIMADO_S["texto_regex"]


def test_frontend_sin_cache(client):
    for path in ("/", "/static/app.js", "/static/styles.css"):
        assert client.get(path).headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/api/metodos").headers
