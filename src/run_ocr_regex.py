"""Parte 2: PDF escaneado -> imagen -> OCR -> regex (mismas reglas que la Parte 1).

Uso:  python -m src.run_ocr_regex [--engine tesseract] [--dpi 250] [--pre binarize] [pdf ...]
      (sin PDFs: pdfs/*_imagen.pdf)

Evidencias guardadas por PDF (<stem>) y motor (<engine>):
  resultados/imagenes/<stem>/pagina_<n>.png          página renderizada
  resultados/imagenes/<stem>/pagina_<n>_<pre>.png    imagen preprocesada enviada al OCR
  resultados/ocr/<engine>/<stem>.json                salida original: palabras, cajas y confianza por página
  resultados/ocr/<engine>/<stem>.txt                 texto reconstruido con disposición (entrada de la regex)
  resultados/json/ocr_regex_<engine>/<stem>.json     campos extraídos
"""
import argparse
import json
import time
from pathlib import Path

from . import ocr, render
from .pdf_text import join_pages
from .regex_extractor import extract

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "resultados"


def process(pdf_path: Path, engine, dpi: int, pre: str) -> dict:
    t0 = time.perf_counter()
    images = render.render_pages(str(pdf_path), dpi=dpi)
    t_render = time.perf_counter() - t0

    img_dir = RES / "imagenes" / pdf_path.stem
    img_dir.mkdir(parents=True, exist_ok=True)
    raw_pages, text_pages = [], []
    for n, img in enumerate(images, 1):
        img.save(img_dir / f"pagina_{n}.png")
        ocr_img = ocr.preprocess(img, pre)
        if pre != "none":
            ocr_img.save(img_dir / f"pagina_{n}_{pre}.png")
        words = engine.read(ocr_img)
        raw_pages.append({"pagina": n, "ancho": img.width, "alto": img.height,
                          "palabras": ocr.words_to_json(words)})
        text_pages.append(ocr.layout_text(words))
    t_ocr = time.perf_counter() - t0 - t_render

    text = join_pages(text_pages)
    result = extract(text)
    out_dir = RES / "ocr" / engine.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{pdf_path.stem}.json").write_text(
        json.dumps({"config": engine.config, "dpi": dpi, "preprocesado": pre, "paginas": raw_pages}, ensure_ascii=False), encoding="utf-8")
    (out_dir / f"{pdf_path.stem}.txt").write_text(text, encoding="utf-8")

    return {
        "archivo": pdf_path.name,
        "metodo": f"ocr({engine.name})+regex",
        "ocr": {**engine.config, "dpi": dpi, "preprocesado": pre},
        "paginas": len(images),
        "tiempo_s": {"render": round(t_render, 3), "ocr": round(t_ocr, 3),
                     "total": round(time.perf_counter() - t0, 3)},
        "error": None,
        **result,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="*", type=Path)
    ap.add_argument("--engine", default="tesseract", choices=sorted(ocr.ENGINES))
    ap.add_argument("--dpi", type=int, default=render.DEFAULT_DPI)
    ap.add_argument("--pre", default="binarize", choices=["none", "gray", "binarize"])
    args = ap.parse_args()

    paths = args.pdfs or sorted((ROOT / "pdfs").glob("*_imagen.pdf"))
    t0 = time.perf_counter()
    engine = ocr.get_engine(args.engine)
    print(f"Motor {args.engine} cargado en {time.perf_counter() - t0:.2f}s")

    out_dir = RES / "json" / f"ocr_regex_{args.engine}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        out = process(path, engine, args.dpi, args.pre)
        (out_dir / f"{path.stem}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        nulls = [k for k, v in out["campos"].items() if v is None]
        print(f"{path.name}: {len(out['campos']) - len(nulls)}/{len(out['campos'])} campos, "
              f"{len(out['lineas'])} líneas, {out['tiempo_s']['total']}s" + (f"  null: {nulls}" if nulls else ""))


if __name__ == "__main__":
    main()
