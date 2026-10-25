"""Parte adicional: OCR + LLM frente a OCR + regex, sobre el mismo texto OCR guardado.

Uso:  python -m src.benchmark_llm                                   (modelos por defecto, todas las variantes)
      python -m src.benchmark_llm --models qwen2.5-1.5b-hf --variants original

Entrada: resultados/benchmark_ocr/tesseract_binarize/<pdf>.txt (OCR elegido en el paso 5) y sus variantes
(src/perturb.py). Cada modelo se ejecuta en un proceso nuevo para medir carga y RAM pico.

Salida en resultados/llm/:
  textos/<variante>/<pdf>.txt              texto exacto enviado (y usado por la regex)
  <método>/<variante>/<pdf>.json           resultado; para el LLM incluye prompt completo, respuestas y reintentos
  resumen.json, resumen.md
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import evaluate
from .metrics import PeakRSS, _mb, hardware
from .perturb import VARIANTS
from .llm_extractor import JSON_SCHEMA, PROMPT, SYSTEM
from .regex_extractor import extract

ROOT = Path(__file__).resolve().parent.parent
OCR_DIR = ROOT / "resultados" / "benchmark_ocr" / "tesseract_binarize"
OUT = ROOT / "resultados" / "llm"
DEFAULT_MODELS = ["qwen2.5-1.5b-q4", "qwen2.5-3b-q4"]
PROMPT_DOC = (f"[system]\n{SYSTEM}\n\n[user]\n{PROMPT}\n\n[esquema JSON impuesto con gramática en llama.cpp]\n"
              f"{json.dumps(JSON_SCHEMA, ensure_ascii=False, indent=2)}\n")


def stems() -> list[str]:
    return sorted(p.stem for p in OCR_DIR.glob("*.txt"))


def write_texts() -> None:
    for variant, fn in VARIANTS.items():
        d = OUT / "textos" / variant
        d.mkdir(parents=True, exist_ok=True)
        for stem in stems():
            (d / f"{stem}.txt").write_text(fn((OCR_DIR / f"{stem}.txt").read_text(encoding="utf-8")), encoding="utf-8")


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _row(method: str, variant: str, docs: list[dict]) -> dict:
    return {"metodo": method, "variante": variant, "n": len(docs),
            **{k: sum(d[k] for d in docs) for k in ("ok", "null", "error", "lineas_celdas_ok", "lineas_celdas")},
            "tiempo_medio_s": round(sum(d.get("tiempo_s", 0) for d in docs) / len(docs), 2)}


def run_regex(variants: list[str]) -> list[dict]:
    rows = []
    for variant in variants:
        docs = []
        for stem in stems():
            text = (OUT / "textos" / variant / f"{stem}.txt").read_text(encoding="utf-8")
            t = time.perf_counter()
            res = extract(text)
            ev = evaluate.compare(res, evaluate.load_gold(stem))
            _save(OUT / "regex" / variant / f"{stem}.json", {**res, "evaluacion": ev})
            docs.append({**ev, "tiempo_s": time.perf_counter() - t})
        rows.append(_row("ocr+regex", variant, docs))
    return rows


def _new_stats() -> dict:
    return {"json_valido_1er_intento": 0, "reintentos": 0, "fallos_formato": 0, "descartados": 0,
            "descartados_que_eran_error": 0, "descartados_que_eran_correctos": 0, "tokens_generados": 0}


def score_doc(model_id: str, variant: str, stem: str, res: dict, config: dict, stats: dict) -> tuple[dict, dict]:
    """Evalúa (verificado y sin verificar), guarda el JSON del documento y acumula estadísticas."""
    gold = evaluate.load_gold(stem)
    ev = evaluate.compare(res, gold)
    ev_raw = evaluate.compare(res["sin_verificar"], gold)
    _save(OUT / model_id / variant / f"{stem}.json",
          {**res, "config": config, "evaluacion": ev, "evaluacion_sin_verificar": ev_raw})
    intentos = res["traza"]["intentos"]
    stats["json_valido_1er_intento"] += intentos[0]["valido"]
    stats["reintentos"] += len(intentos) - 1
    stats["fallos_formato"] += res["error"] is not None
    stats["tokens_generados"] += sum(a["completion_tokens"] for a in intentos)
    for k in res["descartados_sin_evidencia"]:  # solo campos de cabecera (las celdas se cuentan aparte)
        if k in ev_raw["campos"]:
            stats["descartados"] += 1
            stats[f"descartados_que_eran_{'error' if ev_raw['campos'][k] == 'error' else 'correctos'}"] += 1
    return {**ev, "tiempo_s": res["tiempo_s"]}, {**ev_raw, "tiempo_s": res["tiempo_s"]}


def worker(model_id: str, variants: list[str]) -> dict:
    import psutil

    from .llm_extractor import extract_llm, get_backend

    proc = psutil.Process()
    sampler = PeakRSS(proc)
    sampler.start()
    rss0 = proc.memory_info().rss
    t0 = time.perf_counter()
    backend = get_backend(model_id)
    load_s = time.perf_counter() - t0
    rss_loaded = proc.memory_info().rss

    rows, extra = [], {}
    for variant in variants:
        docs, raw_docs, stats = [], [], _new_stats()
        for stem in stems():
            text = (OUT / "textos" / variant / f"{stem}.txt").read_text(encoding="utf-8")
            d, r = score_doc(model_id, variant, stem, extract_llm(text, backend), backend.config, stats)
            docs.append(d)
            raw_docs.append(r)
        rows.append(_row(f"ocr+llm:{model_id}", variant, docs))
        rows.append(_row(f"ocr+llm:{model_id} (sin verificar)", variant, raw_docs))
        extra[variant] = stats
    sampler.stop()
    return {"model_id": model_id, "config": backend.config, "carga_s": round(load_s, 2),
            "ram_mb": {"inicio": _mb(rss0 // 1024), "tras_carga": _mb(rss_loaded // 1024),
                       "pico": _mb(sampler.peak // 1024)},
            "filas": rows, "estadisticas": extra}


def reevaluate(run: dict) -> dict:
    """Recalcula resultados y evaluación desde las respuestas guardadas del modelo, sin volver a generarlas.
    Conserva los tiempos y la RAM medidos en la ejecución original."""
    from .llm_extractor import finalize, parse_response

    model_id, rows, extra = run["model_id"], [], {}
    for variant in run["estadisticas"]:
        docs, raw_docs, stats = [], [], _new_stats()
        for stem in stems():
            old = json.loads((OUT / model_id / variant / f"{stem}.json").read_text(encoding="utf-8"))
            text = (OUT / "textos" / variant / f"{stem}.txt").read_text(encoding="utf-8")
            intentos = old["traza"]["intentos"]
            data = parse_response(intentos[-1]["respuesta"]) if intentos[-1]["valido"] else None
            res = finalize(data, text, old["traza"]["mensajes"], intentos, old["tiempo_s"])
            d, r = score_doc(model_id, variant, stem, res, old["config"], stats)
            docs.append(d)
            raw_docs.append(r)
        rows.append(_row(f"ocr+llm:{model_id}", variant, docs))
        rows.append(_row(f"ocr+llm:{model_id} (sin verificar)", variant, raw_docs))
        extra[variant] = stats
    return {**run, "filas": rows, "estadisticas": extra}


def summary_md(hw: dict, regex_rows: list[dict], runs: list[dict]) -> str:
    out = [f"# OCR + LLM frente a OCR + regex\n\nHardware: `{json.dumps(hw, ensure_ascii=False)}`\n",
           "Texto de entrada: OCR Tesseract (binarizado) de las 5 facturas. 75 campos y 175 celdas por variante.\n",
           "| Método | Variante | Campos ok | null | error | Celdas líneas | s/doc |", "|---|---|---|---|---|---|---|"]
    for r in regex_rows + [row for run in runs for row in run["filas"]]:
        out.append(f"| {r['metodo']} | {r['variante']} | {r['ok']}/{15 * r['n']} | {r['null']} | {r['error']} | "
                   f"{r['lineas_celdas_ok']}/{r['lineas_celdas']} | {r['tiempo_medio_s']} |")
    out.append("\n## Modelos\n")
    for run in runs:
        out.append(f"### {run['model_id']}\n- Config: `{json.dumps(run['config'], ensure_ascii=False)}`\n"
                   f"- Carga: {run['carga_s']} s · RAM (MB): {run['ram_mb']}\n")
        for v, s in run["estadisticas"].items():
            out.append(f"- {v}: `{json.dumps(s, ensure_ascii=False)}`")
        out.append("")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    ap.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    ap.add_argument("--reevaluar", action="store_true",
                    help="recalcula desde las respuestas guardadas, sin ejecutar los modelos")
    args = ap.parse_args()

    if args.worker:
        print(json.dumps(worker(args.worker, args.variants), ensure_ascii=False))
        return

    write_texts()
    regex_rows = run_regex(list(VARIANTS))
    summary_path = OUT / "resumen.json"
    previous = json.loads(summary_path.read_text()) if summary_path.exists() else {"runs": []}
    runs = {r["model_id"]: r for r in previous["runs"]}
    for model_id in [] if args.reevaluar else args.models:
        print(f"→ {model_id} ({', '.join(args.variants)}) ...", flush=True)
        p = subprocess.run([sys.executable, "-W", "ignore", "-m", "src.benchmark_llm", "--worker", model_id,
                            "--variants", *args.variants], cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            print(p.stderr[-3000:])
            continue
        runs[model_id] = json.loads(p.stdout.strip().splitlines()[-1])
        print(f"  carga {runs[model_id]['carga_s']} s, RAM pico {runs[model_id]['ram_mb']['pico']} MB")
    if args.reevaluar:
        runs = {m: reevaluate(r) for m, r in runs.items()}
    hw = previous.get("hardware") or hardware()
    (OUT / "prompt.txt").write_text(PROMPT_DOC, encoding="utf-8")
    summary_path.write_text(json.dumps({"hardware": hw, "regex": regex_rows, "runs": list(runs.values())},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
    md = summary_md(hw, regex_rows, list(runs.values()))
    (OUT / "resumen.md").write_text(md, encoding="utf-8")
    print(md.split("## Modelos")[0])


if __name__ == "__main__":
    main()
