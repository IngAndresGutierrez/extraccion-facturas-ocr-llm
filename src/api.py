"""API FastAPI: sirve la interfaz y atiende las peticiones de extracción.

  GET  /                          index.html
  GET  /static/...                app.js, styles.css
  GET  /api/metodos               métodos disponibles
  POST /api/extract               multipart: file (PDF) + method -> 202 {"job_id"}
  GET  /api/jobs/{id}             estado: en_cola | procesando (+ etapa) | completado (+ resultado) | error (+ mensaje)
  GET  /api/jobs/{id}/descarga    JSON del resultado como archivo

El trabajo se ejecuta en segundo plano porque OCR + LLM tarda ~1 min. Un único hilo de trabajo: los métodos
usan toda la CPU y en paralelo solo se estorbarían. El estado vive en memoria (no se pide base de datos).
"""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
MAX_BYTES = 20 * 1024 * 1024

app = FastAPI(title="Extracción de facturas PDF")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _update(job_id: str, **fields) -> None:
    with _lock:
        _jobs[job_id].update(fields)


def _work(job_id: str, pdf: bytes, method: str, filename: str) -> None:
    _update(job_id, estado="procesando", etapa="Iniciando", inicio=time.time())
    try:
        result = pipeline.run(pdf, method, filename, job_id, progress=lambda etapa: _update(job_id, etapa=etapa))
        _update(job_id, estado="completado", etapa=None, resultado=result)
    except pipeline.ExtractionError as e:
        _update(job_id, estado="error", etapa=None, mensaje=str(e))
    except Exception as e:  # noqa: BLE001 — cualquier fallo inesperado debe llegar al usuario, no colgar el trabajo
        _update(job_id, estado="error", etapa=None, mensaje=f"Error interno al procesar el PDF: {type(e).__name__}: {e}")
    finally:
        _update(job_id, fin=time.time())


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/metodos")
def metodos() -> dict:
    return pipeline.METHODS


@app.post("/api/extract", status_code=202)
async def extract(file: UploadFile = File(...), method: str = Form(...)) -> dict:
    if method not in pipeline.METHODS:
        raise HTTPException(400, f"Método desconocido «{method}». Opciones: {', '.join(pipeline.METHODS)}.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "El archivo está vacío.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"El archivo supera el máximo de {MAX_BYTES // 1024 // 1024} MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, f"«{file.filename}» no es un PDF válido (falta la cabecera %PDF).")
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        en_cola = sum(j["estado"] in ("en_cola", "procesando") for j in _jobs.values())
        _jobs[job_id] = {"id": job_id, "archivo": file.filename, "metodo": method, "estado": "en_cola",
                         "etapa": f"En cola ({en_cola} trabajo(s) delante)" if en_cola else "En cola",
                         "creado": time.time()}
    _executor.submit(_work, job_id, data, method, file.filename or "documento.pdf")
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    with _lock:
        j = dict(_jobs.get(job_id) or {})
    if not j:
        raise HTTPException(404, "Trabajo no encontrado (puede que el servidor se haya reiniciado).")
    if j.get("inicio"):
        j["transcurrido_s"] = round((j.get("fin") or time.time()) - j["inicio"], 1)
    return j


@app.get("/api/jobs/{job_id}/descarga")
def descarga(job_id: str) -> JSONResponse:
    j = job(job_id)
    if j["estado"] != "completado":
        raise HTTPException(409, "El resultado todavía no está disponible.")
    name = Path(j["archivo"]).stem + f"_{j['metodo']}.json"
    return JSONResponse(j["resultado"], headers={"Content-Disposition": f'attachment; filename="{name}"'})
