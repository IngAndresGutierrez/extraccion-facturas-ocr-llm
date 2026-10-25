"""Orquestación de los tres métodos de extracción para la interfaz web (sin dependencias de FastAPI).

  texto_regex   texto seleccionable (PyMuPDF) + regex
  ocr_regex     render 250 DPI + binarización + Tesseract + regex
  ocr_llm       render 250 DPI + binarización + Tesseract + LLM local (llama.cpp) con verificación de evidencia

Cada ejecución guarda sus evidencias en resultados/web/<id>/ (texto leído, salida original del OCR, JSON).
"""
import json
import os
import time
from pathlib import Path
from typing import Callable

import pymupdf

from . import ocr, pdf_text, render
from .regex_extractor import extract

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "resultados" / "web"
METHODS = {
    "texto_regex": "Texto seleccionable + regex",
    "ocr_regex": "OCR (Tesseract) + regex",
    "ocr_llm": "OCR (Tesseract) + LLM local",
}
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5-3b-q4")
OCR_PRE = "binarize"


class ExtractionError(Exception):
    """Error esperado, con un mensaje pensado para mostrarse al usuario."""


# Los motores se cargan una vez y se reutilizan entre peticiones (el LLM tarda ~4 s y ocupa ~4 GB).
_engines: dict = {}


def _tesseract():
    if "tesseract" not in _engines:
        _engines["tesseract"] = ocr.get_engine("tesseract")
    return _engines["tesseract"]


def _llm():
    if "llm" not in _engines:
        from .download_models import model_path
        if not model_path(LLM_MODEL).exists():
            raise ExtractionError(f"El modelo {LLM_MODEL} no está descargado. Ejecuta: "
                                  f"docker compose run --rm app python -m src.download_models {LLM_MODEL}")
        from .llm_extractor import get_backend
        _engines["llm"] = get_backend(LLM_MODEL)
    return _engines["llm"]


def _open(pdf: bytes) -> list[str]:
    try:
        return pdf_text.read_pages(pdf)
    except (pymupdf.FileDataError, RuntimeError, ValueError) as e:
        raise ExtractionError(f"No se pudo abrir el PDF (¿está dañado?): {e}") from e


def _ocr_text(pdf: bytes, job_dir: Path, progress: Callable[[str], None]) -> tuple[str, dict]:
    progress("Renderizando páginas a 250 DPI")
    images = render.render_pages(pdf)
    engine = _tesseract()
    pages_text, raw = [], []
    for n, img in enumerate(images, 1):
        progress(f"OCR de la página {n} de {len(images)}")
        prepared = ocr.preprocess(img, OCR_PRE)
        prepared.save(job_dir / f"pagina_{n}_{OCR_PRE}.png")
        words = engine.read(prepared)
        raw.append({"pagina": n, "palabras": ocr.words_to_json(words)})
        pages_text.append(ocr.layout_text(words))
    (job_dir / "ocr_original.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return pdf_text.join_pages(pages_text), {**engine.config, "dpi": render.DEFAULT_DPI, "preprocesado": OCR_PRE}


def run(pdf: bytes, method: str, filename: str, job_id: str,
        progress: Callable[[str], None] = lambda _: None) -> dict:
    """Procesa un PDF con el método indicado. Lanza ExtractionError con un mensaje comprensible."""
    if method not in METHODS:
        raise ExtractionError(f"Método desconocido: {method}. Opciones: {', '.join(METHODS)}")
    job_dir = OUT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    avisos, detalles = [], {}

    progress("Leyendo el PDF")
    pages = _open(pdf)
    has_text = pdf_text.has_text_layer(pages)

    if method == "texto_regex":
        if not has_text:
            raise ExtractionError("Este PDF no tiene texto seleccionable (es una imagen escaneada). "
                                  "Elige «OCR + regex» u «OCR + LLM».")
        text = pdf_text.join_pages(pages)
        progress("Aplicando regex")
        result = extract(text)
    else:
        if has_text:
            avisos.append("El PDF tiene texto seleccionable: «Texto + regex» sería más rápido y exacto.")
        text, detalles["ocr"] = _ocr_text(pdf, job_dir, progress)
        if method == "ocr_regex":
            progress("Aplicando regex")
            result = extract(text)
        else:
            progress("Cargando el LLM" if "llm" not in _engines else "Consultando el LLM")
            backend = _llm()
            progress("Consultando el LLM (≈ 45 s por página en CPU)")
            from .llm_extractor import extract_llm
            llm = extract_llm(text, backend)
            if llm["error"]:
                raise ExtractionError(llm["error"])
            result = {"campos": llm["campos"], "lineas": llm["lineas"]}
            detalles["llm"] = {"config": backend.config, "descartados_sin_evidencia": llm["descartados_sin_evidencia"],
                               "intentos": len(llm["traza"]["intentos"])}
            if llm["descartados_sin_evidencia"]:
                avisos.append(f"Se descartaron {len(llm['descartados_sin_evidencia'])} valores del LLM que no "
                              "aparecen en el texto leído.")
            (job_dir / "llm_traza.json").write_text(json.dumps(llm["traza"], ensure_ascii=False, indent=2),
                                                    encoding="utf-8")

    nulls = [k for k, v in result["campos"].items() if v is None]
    if nulls:
        avisos.append(f"{len(nulls)} campo(s) sin valor (null): revisar manualmente.")
    out = {
        "archivo": filename,
        "metodo": method,
        "metodo_nombre": METHODS[method],
        "paginas": len(pages),
        "tiempo_s": round(time.perf_counter() - t0, 2),
        "avisos": avisos,
        **result,
        "detalles": detalles,
        "texto_leido": text,
    }
    (job_dir / "texto_leido.txt").write_text(text, encoding="utf-8")
    (job_dir / "resultado.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
