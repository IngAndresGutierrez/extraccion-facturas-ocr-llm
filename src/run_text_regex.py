"""Parte 1: texto seleccionable + regex sobre los PDFs indicados.

Uso:  python -m src.run_text_regex pdfs/Factura_01_texto.pdf pdfs/Factura_02_texto.pdf ...
      python -m src.run_text_regex            (todos los PDFs de pdfs/)

Guarda en resultados/texto/<pdf>.txt el texto leído y en resultados/json/texto_regex/<pdf>.json el resultado.
"""
import json
import sys
import time
from pathlib import Path

from . import pdf_text
from .regex_extractor import extract

ROOT = Path(__file__).resolve().parent.parent
OUT_TEXT = ROOT / "resultados" / "texto"
OUT_JSON = ROOT / "resultados" / "json" / "texto_regex"


def process(pdf_path: Path) -> tuple[dict, str]:
    t0 = time.perf_counter()
    pages = pdf_text.read_pages(str(pdf_path))
    text = pdf_text.join_pages(pages)
    if pdf_text.has_text_layer(pages):
        result = extract(text)
        error = None
    else:
        result = extract("")  # todas las claves a null
        error = "El PDF no tiene texto seleccionable: usa el método OCR."
    return {
        "archivo": pdf_path.name,
        "metodo": "texto+regex",
        "paginas": len(pages),
        "tiempo_s": round(time.perf_counter() - t0, 4),
        "error": error,
        **result,
    }, text


def main(argv: list[str]) -> None:
    paths = [Path(p) for p in argv] or sorted((ROOT / "pdfs").glob("*.pdf"))
    OUT_TEXT.mkdir(parents=True, exist_ok=True)
    OUT_JSON.mkdir(parents=True, exist_ok=True)
    for path in paths:
        out, text = process(path)
        (OUT_TEXT / f"{path.stem}.txt").write_text(text, encoding="utf-8")
        (OUT_JSON / f"{path.stem}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        nulls = [k for k, v in out["campos"].items() if v is None]
        print(f"{path.name}: {len(out['campos']) - len(nulls)}/{len(out['campos'])} campos, "
              f"{len(out['lineas'])} líneas, {out['tiempo_s']}s" + (f"  [{out['error']}]" if out["error"] else "")
              + (f"  null: {nulls}" if nulls and not out["error"] else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
