"""API FastAPI: sirve la interfaz y atiende las peticiones de extracción.

  GET    /                          index.html
  GET    /static/...                app.js, styles.css
  GET    /api/metodos               métodos disponibles
  POST   /api/analizar              multipart: file (PDF) -> páginas, si tiene texto y método sugerido (sin OCR)
  POST   /api/extract               multipart: file (PDF) + method -> 202 {"job_id"}
  GET    /api/jobs/{id}             estado: en_cola | procesando (+ etapa) | completado (+ resultado) | error (+ mensaje)
                                    | cancelado; incluye estimado_s (duración prevista según trabajos anteriores)
  DELETE /api/jobs/{id}             cancela: en cola se descarta; en proceso se detiene en la siguiente etapa
  GET    /api/jobs/{id}/descarga    JSON del resultado como archivo

El trabajo se ejecuta en segundo plano porque OCR + LLM tarda ~1 min. Un único hilo de trabajo: los métodos
usan toda la CPU y en paralelo solo se estorbarían. El estado vive en memoria (no se pide base de datos).
"""
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
MAX_BYTES = 20 * 1024 * 1024
# Duración prevista (s) hasta que haya trabajos completados con los que promediar.
ESTIMADO_S = {"texto_regex": 1, "ocr_regex": 3, "ocr_llm": 60}

app = FastAPI(title="Extracción de facturas PDF")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """Sin Cache-Control el navegador reutiliza index.html, app.js y styles.css viejos tras un cambio.
    no-cache obliga a revalidar con el ETag: si no cambiaron, la respuesta es un 304 sin cuerpo."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response

_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict] = {}
_futures: dict[str, Future] = {}
_lock = threading.Lock()


class Cancelado(Exception):
    """El usuario canceló el trabajo; se lanza desde el callback de progreso entre etapas."""


def _update(job_id: str, **fields) -> None:
    with _lock:
        _jobs[job_id].update(fields)


def _progress(job_id: str, etapa: str) -> None:
    with _lock:
        if _jobs[job_id].get("cancelar"):
            raise Cancelado
        _jobs[job_id]["etapa"] = etapa


def _work(job_id: str, pdf: bytes, method: str, filename: str) -> None:
    _update(job_id, estado="procesando", etapa="Iniciando", inicio=time.time())
    try:
        result = pipeline.run(pdf, method, filename, job_id, progress=lambda etapa: _progress(job_id, etapa))
        _update(job_id, estado="completado", etapa=None, resultado=result)
    except Cancelado:
        _update(job_id, estado="cancelado", etapa=None)
    except pipeline.ExtractionError as e:
        _update(job_id, estado="error", etapa=None, mensaje=str(e))
    except Exception as e:  # noqa: BLE001 — cualquier fallo inesperado debe llegar al usuario, no colgar el trabajo
        _update(job_id, estado="error", etapa=None, mensaje=f"Error interno al procesar el PDF: {type(e).__name__}: {e}")
    finally:
        _update(job_id, fin=time.time())


def _estimado(method: str) -> float:
    """Media de los últimos 5 trabajos completados con el mismo método (llamar con _lock tomado)."""
    hechos = sorted((j for j in _jobs.values() if j["metodo"] == method and j["estado"] == "completado"),
                    key=lambda j: j["fin"])[-5:]
    if not hechos:
        return ESTIMADO_S[method]
    return round(sum(j["fin"] - j["inicio"] for j in hechos) / len(hechos), 1)


async def _read_pdf(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(400, "El archivo está vacío.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"El archivo supera el máximo de {MAX_BYTES // 1024 // 1024} MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, f"«{file.filename}» no es un PDF válido (falta la cabecera %PDF).")
    return data


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/metodos")
def metodos() -> dict:
    return pipeline.METHODS


@app.post("/api/analizar")
async def analizar(file: UploadFile = File(...)) -> dict:
    data = await _read_pdf(file)
    try:
        return pipeline.analyze(data)
    except pipeline.ExtractionError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/extract", status_code=202)
async def extract(file: UploadFile = File(...), method: str = Form(...)) -> dict:
    if method not in pipeline.METHODS:
        raise HTTPException(400, f"Método desconocido «{method}». Opciones: {', '.join(pipeline.METHODS)}.")
    data = await _read_pdf(file)
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        en_cola = sum(j["estado"] in ("en_cola", "procesando") for j in _jobs.values())
        _jobs[job_id] = {"id": job_id, "archivo": file.filename, "metodo": method, "estado": "en_cola",
                         "etapa": f"En cola ({en_cola} trabajo(s) delante)" if en_cola else "En cola",
                         "creado": time.time()}
        _futures[job_id] = _executor.submit(_work, job_id, data, method, file.filename or "documento.pdf")
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    with _lock:
        j = dict(_jobs.get(job_id) or {})
        if j:
            j["estimado_s"] = _estimado(j["metodo"])
    if not j:
        raise HTTPException(404, "Trabajo no encontrado (puede que el servidor se haya reiniciado).")
    j.pop("cancelar", None)
    if j.get("inicio"):
        j["transcurrido_s"] = round((j.get("fin") or time.time()) - j["inicio"], 1)
    return j


@app.delete("/api/jobs/{job_id}")
def cancelar(job_id: str) -> dict:
    with _lock:
        j = _jobs.get(job_id)
        if not j:
            raise HTTPException(404, "Trabajo no encontrado (puede que el servidor se haya reiniciado).")
        if j["estado"] not in ("en_cola", "procesando"):
            raise HTTPException(409, f"El trabajo ya terminó ({j['estado']}).")
        if _futures[job_id].cancel():  # aún en cola: no llega a ejecutarse
            j.update(estado="cancelado", etapa=None)
        else:  # en proceso: se detiene al empezar la siguiente etapa
            j.update(cancelar=True, etapa="Cancelando…")
        return {"estado": j["estado"]}


@app.get("/api/jobs/{job_id}/descarga")
def descarga(job_id: str) -> JSONResponse:
    j = job(job_id)
    if j["estado"] != "completado":
        raise HTTPException(409, "El resultado todavía no está disponible.")
    name = Path(j["archivo"]).stem + f"_{j['metodo']}.json"
    return JSONResponse(j["resultado"], headers={"Content-Disposition": f'attachment; filename="{name}"'})
