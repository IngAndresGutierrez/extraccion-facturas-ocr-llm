"""Comparación de una extracción con la referencia (gold) transcrita a mano en evaluacion/gold/.

Por campo distingue tres resultados, porque no pesan igual en una factura:
  ok      valor idéntico al gold
  null    no extraído (se ve y se revisa)
  error   valor distinto del gold (más grave: parece correcto y puede pasar sin revisión)
Líneas: precisión por celda; cada línea se empareja por su referencia (si se lee mal, la línea cuenta como perdida).
"""
import json
from pathlib import Path

from .schema import CAMPOS, CAMPOS_LINEA

GOLD_DIR = Path(__file__).resolve().parent.parent / "evaluacion" / "gold"


def load_gold(stem: str) -> dict:
    return json.loads((GOLD_DIR / f"{stem}.json").read_text(encoding="utf-8"))


def compare(pred: dict, gold: dict) -> dict:
    status = {}
    for k in CAMPOS:
        p, g = pred["campos"].get(k), gold["campos"][k]
        status[k] = "ok" if p == g else ("null" if p is None else "error")
    pred_lines = {l.get("referencia"): l for l in pred.get("lineas", [])}
    cells = sum(len(CAMPOS_LINEA) for _ in gold["lineas"])
    good = sum(pred_lines.get(g["referencia"], {}).get(k) == v for g in gold["lineas"] for k, v in g.items())
    counts = {s: sum(v == s for v in status.values()) for s in ("ok", "null", "error")}
    return {**counts, "campos": status, "lineas_celdas_ok": good, "lineas_celdas": cells,
            "errores": {k: {"pred": pred["campos"].get(k), "gold": gold["campos"][k]}
                        for k, s in status.items() if s == "error"}}
