"""Paso 5: comparación de motores OCR en CPU (calidad de campos, tiempo, RAM, carga).

Uso:  python -m src.benchmark_ocr                      (todas las configuraciones)
      python -m src.benchmark_ocr --only easyocr:none

Cada configuración se ejecuta en un proceso nuevo para que la RAM medida (pico de RSS) incluya la carga
del modelo y no se mezcle con la de otros motores. Se procesan las 5 facturas renderizadas como imagen:
las 2 escaneadas y las 3 de texto (estas sin usar su capa de texto), comparando con evaluacion/gold/.

Salida: resultados/benchmark_ocr/<motor>_<pre>/<pdf>.txt|.json, resumen.json y resumen.md
"""
import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "resultados" / "benchmark_ocr"
CONFIGS = ["tesseract:none", "tesseract:binarize", "easyocr:none", "easyocr:binarize", "doctr:none", "doctr:binarize"]


def _mb(kb: int) -> float:
    return round(kb / 1024, 1)


class PeakRSS(threading.Thread):
    """Muestrea cada 20 ms la RSS del proceso más la de sus hijos vivos (tesseract es un binario aparte).
    ru_maxrss de RUSAGE_CHILDREN no sirve: incluye la memoria heredada por fork() antes del exec."""

    def __init__(self, proc):
        super().__init__(daemon=True)
        self.proc, self.peak, self.peak_children, self._done = proc, 0, 0, threading.Event()

    def run(self):
        import psutil
        while not self._done.wait(0.02):
            try:
                children = sum(c.memory_info().rss for c in self.proc.children(recursive=True))
            except psutil.Error:
                children = 0
            self.peak_children = max(self.peak_children, children)
            self.peak = max(self.peak, self.proc.memory_info().rss + children)

    def stop(self) -> None:
        self._done.set()
        self.join()


def worker(engine_name: str, pre: str) -> dict:
    """Se ejecuta en un subproceso: carga el motor, procesa los PDFs y mide."""
    import psutil

    from . import evaluate, ocr, render
    from .pdf_text import join_pages
    from .regex_extractor import extract

    proc = psutil.Process()
    rss_start = proc.memory_info().rss
    sampler = PeakRSS(proc)
    sampler.start()
    t0 = time.perf_counter()
    engine = ocr.get_engine(engine_name)
    load_s = time.perf_counter() - t0
    rss_loaded = proc.memory_info().rss

    out_dir = OUT / f"{engine_name}_{pre}"
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = []
    for pdf in sorted((ROOT / "pdfs").glob("*.pdf")):
        t = time.perf_counter()
        pages = [ocr.layout_text(engine.read(ocr.preprocess(img, pre))) for img in render.render_pages(str(pdf))]
        result = extract(join_pages(pages))
        secs = time.perf_counter() - t
        ev = evaluate.compare(result, evaluate.load_gold(pdf.stem))
        (out_dir / f"{pdf.stem}.txt").write_text(join_pages(pages), encoding="utf-8")
        (out_dir / f"{pdf.stem}.json").write_text(json.dumps({**result, "evaluacion": ev}, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
        docs.append({"pdf": pdf.stem, "tiempo_s": round(secs, 2), **{k: ev[k] for k in ("ok", "null", "error")},
                     "lineas_celdas_ok": ev["lineas_celdas_ok"], "lineas_celdas": ev["lineas_celdas"],
                     "errores": ev["errores"], "nulls": [k for k, s in ev["campos"].items() if s == "null"]})

    sampler.stop()
    self_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KB en Linux; pico exacto del proceso Python
    try:
        import torch
        threads = torch.get_num_threads()
    except ImportError:
        threads = None
    return {"config": {**engine.config, "preprocesado": pre, "dpi": render.DEFAULT_DPI},
            "carga_s": round(load_s, 2),
            "ram_mb": {"inicio": _mb(rss_start // 1024), "tras_carga": _mb(rss_loaded // 1024),
                       "pico_python": _mb(self_peak), "pico_hijos": _mb(sampler.peak_children // 1024),
                       "pico_total": _mb(max(sampler.peak, self_peak * 1024) // 1024)},
            "torch_threads": threads, "docs": docs}


def hardware() -> dict:
    mem = dict(l.split(":", 1) for l in Path("/proc/meminfo").read_text().splitlines()[:3])
    return {"arquitectura": platform.machine(), "cpus": os.cpu_count(), "so": platform.platform(),
            "ram_total_mb": _mb(int(mem["MemTotal"].split()[0])),
            "ram_disponible_mb": _mb(int(mem["MemAvailable"].split()[0])),
            "host": os.environ.get("HOST_INFO", "no indicado"), "python": platform.python_version()}


def summary_md(hw: dict, runs: list[dict]) -> str:
    rows = ["| Motor | Preproc. | Carga (s) | s/doc (media) | RAM pico (MB) | Campos ok | null | error | Celdas líneas |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        d = r["docs"]
        n = len(d)
        rows.append(f"| {r['config']['engine']} | {r['config']['preprocesado']} | {r['carga_s']} | "
                    f"{sum(x['tiempo_s'] for x in d) / n:.2f} | {r['ram_mb']['pico_total']} | "
                    f"{sum(x['ok'] for x in d)}/{15 * n} | {sum(x['null'] for x in d)} | {sum(x['error'] for x in d)} | "
                    f"{sum(x['lineas_celdas_ok'] for x in d)}/{sum(x['lineas_celdas'] for x in d)} |")
    detail = []
    for r in runs:
        detail.append(f"\n### {r['config']['engine']} · {r['config']['preprocesado']}\n`{json.dumps(r['config'], ensure_ascii=False)}`\n")
        for x in r["docs"]:
            errs = "; ".join(f"{k}: {v['pred']!r} ≠ {v['gold']!r}" for k, v in x["errores"].items())
            detail.append(f"- {x['pdf']}: {x['ok']}/15 ok, {x['tiempo_s']} s, celdas {x['lineas_celdas_ok']}/{x['lineas_celdas']}"
                          + (f", null: {', '.join(x['nulls'])}" if x["nulls"] else "") + (f", **error**: {errs}" if errs else ""))
    return (f"# Benchmark OCR (CPU)\n\nHardware: `{json.dumps(hw, ensure_ascii=False)}`\n\n"
            f"5 facturas renderizadas a 250 DPI; 15 campos por factura (75) y 35 celdas de líneas por factura (175).\n\n"
            + "\n".join(rows) + "\n\n## Detalle por documento\n" + "\n".join(detail) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    ap.add_argument("--only", nargs="*", default=CONFIGS)
    args = ap.parse_args()

    if args.worker:
        engine_name, pre = args.worker.split(":")
        print(json.dumps(worker(engine_name, pre), ensure_ascii=False))
        return

    OUT.mkdir(parents=True, exist_ok=True)
    hw, runs = hardware(), []
    for cfg in args.only:
        print(f"→ {cfg} ...", flush=True)
        p = subprocess.run([sys.executable, "-W", "ignore", "-m", "src.benchmark_ocr", "--worker", cfg],
                           cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            print(p.stderr[-2000:])
            continue
        runs.append(json.loads(p.stdout.strip().splitlines()[-1]))
        r = runs[-1]
        print(f"  carga {r['carga_s']}s, pico {r['ram_mb']['pico_total']} MB, "
              f"ok {sum(x['ok'] for x in r['docs'])}/75, error {sum(x['error'] for x in r['docs'])}")
    (OUT / "resumen.json").write_text(json.dumps({"hardware": hw, "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "resumen.md").write_text(summary_md(hw, runs), encoding="utf-8")
    print(summary_md(hw, runs).split("## Detalle")[0])


if __name__ == "__main__":
    main()
