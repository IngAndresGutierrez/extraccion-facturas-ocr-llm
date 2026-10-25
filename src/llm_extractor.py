"""Extracción de campos con un LLM local (CPU) a partir del texto del OCR.

Flujo:
  1. Prompt con la definición de los campos; se pide copiar cada valor tal como aparece, o null.
  2. Respuesta en JSON (llama.cpp la restringe con una gramática generada desde JSON_SCHEMA).
  3. Validación de formato; si falla, un reintento con el error. Se guardan todos los intentos.
  4. Normalización con las mismas funciones que la regex (normalize.py), no con el LLM.
  5. Verificación de evidencia: un valor que no aparece en el texto del OCR se descarta (null),
     porque un JSON válido puede contener datos inventados.
"""
import json
import re
import time

from . import normalize as norm
from .regex_extractor import NORMALIZERS
from .schema import CAMPOS, CAMPOS_LINEA, resultado_vacio

NULLABLE = {"type": ["string", "null"]}
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "campos": {"type": "object", "properties": {k: NULLABLE for k in CAMPOS},
                   "required": list(CAMPOS), "additionalProperties": False},
        "lineas": {"type": "array", "items": {
            "type": "object", "properties": {k: NULLABLE for k in CAMPOS_LINEA},
            "required": list(CAMPOS_LINEA), "additionalProperties": False}},
    },
    "required": ["campos", "lineas"],
    "additionalProperties": False,
}

SYSTEM = "Eres un sistema de extracción de datos de facturas. Respondes solo con JSON válido."

_FIELD_DOC = "\n".join(f"- {k}: {v['descripcion']}." for k, v in CAMPOS.items())
_LINE_DOC = ("referencia (código del artículo), descripcion, cantidad, precio_unitario, descuento_pct "
             "(porcentaje de descuento), iva_pct (porcentaje de IVA), importe (importe de la línea)")

PROMPT = f"""Extrae los datos de la factura del texto de abajo. El texto procede de un OCR: puede tener errores, \
las columnas pueden aparecer en la misma línea separadas por espacios o en líneas distintas, y las etiquetas \
pueden variar.

Campos (objeto "campos"):
{_FIELD_DOC}

Líneas de producto (lista "lineas", una entrada por fila de la tabla): {_LINE_DOC}.

Reglas:
1. Copia cada valor exactamente como aparece en el texto (mismas cifras, comas, puntos, fechas y mayúsculas). \
No conviertas formatos, no corrijas el OCR y no traduzcas.
2. Si un campo no aparece, es ilegible o hay varios candidatos y no se sabe cuál es, usa null. Nunca inventes \
ni deduzcas un valor; no calcules importes.
3. El emisor es quien emite/vende; el cliente es quien compra. No los confundas.
4. Las líneas de producto se toman solo de la tabla; si no hay tabla, "lineas" es [].
5. Responde solo con un objeto JSON con las claves "campos" y "lineas".

Texto de la factura:
<<<
{{texto}}
>>>"""


def build_messages(text: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROMPT.replace("{texto}", text)}]


# ---------------------------------------------------------------- backends

class LlamaCppBackend:
    """llama.cpp vía llama-cpp-python, modelo GGUF cuantizado, salida restringida por gramática JSON."""

    def __init__(self, model_id: str, n_ctx: int = 4096, n_threads: int | None = None):
        import os

        import llama_cpp
        from .download_models import MODELS, model_path
        self.model_id, self.n_ctx = model_id, n_ctx
        self.n_threads = n_threads or os.cpu_count()
        self._meta = {"runtime": "llama.cpp", "llama_cpp_python": llama_cpp.__version__,
                      "repo": MODELS[model_id][0], "revision": MODELS[model_id][1], "archivo": MODELS[model_id][2]}
        self.llm = llama_cpp.Llama(model_path=str(model_path(model_id)), n_ctx=n_ctx, n_threads=self.n_threads,
                                   seed=0, verbose=False)

    @property
    def config(self) -> dict:
        return {**self._meta, "model_id": self.model_id, "cuantizacion": "Q4_K_M", "n_ctx": self.n_ctx,
                "n_threads": self.n_threads, "temperature": 0.0, "max_tokens": 1500, "salida": "json_schema (gramática)"}

    def generate(self, messages: list[dict]) -> tuple[str, dict]:
        r = self.llm.create_chat_completion(messages=messages, temperature=0.0, max_tokens=1500, seed=0,
                                            response_format={"type": "json_object", "schema": JSON_SCHEMA})
        return r["choices"][0]["message"]["content"], {"prompt_tokens": r["usage"]["prompt_tokens"],
                                                      "completion_tokens": r["usage"]["completion_tokens"]}


class TransformersBackend:
    """Alternativa sobre PyTorch: mismo modelo sin cuantizar (float32), decodificación voraz, sin gramática."""

    def __init__(self, model_id: str, dtype: str = "float32"):
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from .download_models import MODELS, model_path
        self._torch, self.model_id, self.dtype = torch, model_id, dtype
        path = str(model_path(model_id))
        self.tok = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForCausalLM.from_pretrained(path, dtype=getattr(torch, dtype))
        self.model.eval()
        self._meta = {"runtime": "transformers", "transformers": transformers.__version__, "torch": torch.__version__,
                      "repo": MODELS[model_id][0], "revision": MODELS[model_id][1]}

    @property
    def config(self) -> dict:
        return {**self._meta, "model_id": self.model_id, "cuantizacion": f"ninguna ({self.dtype})",
                "torch_threads": self._torch.get_num_threads(), "do_sample": False, "max_new_tokens": 1500,
                "salida": "texto libre + validación"}

    def generate(self, messages: list[dict]) -> tuple[str, dict]:
        inputs = self.tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt",
                                              return_dict=True)
        with self._torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=1500, do_sample=False)
        n_in = inputs["input_ids"].shape[1]
        text = self.tok.decode(out[0][n_in:], skip_special_tokens=True)
        return text, {"prompt_tokens": n_in, "completion_tokens": int(out.shape[1] - n_in)}


def get_backend(name: str):
    if name.endswith("-hf"):
        return TransformersBackend(name)
    return LlamaCppBackend(name)


# ---------------------------------------------------------------- validación y posproceso

def parse_response(raw: str) -> dict:
    """Valida forma: JSON, claves exactas y valores string/null. Lanza ValueError con el motivo."""
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    data = json.loads(s)
    if not isinstance(data, dict) or set(data) != {"campos", "lineas"}:
        raise ValueError("el objeto debe tener exactamente las claves 'campos' y 'lineas'")
    if set(data["campos"]) != set(CAMPOS):
        raise ValueError(f"'campos' debe tener exactamente las claves {list(CAMPOS)}")
    if not isinstance(data["lineas"], list) or any(set(l) != set(CAMPOS_LINEA) for l in data["lineas"]):
        raise ValueError(f"cada línea debe tener exactamente las claves {list(CAMPOS_LINEA)}")
    for v in list(data["campos"].values()) + [v for l in data["lineas"] for v in l.values()]:
        if v is not None and not isinstance(v, str):
            raise ValueError("todos los valores deben ser texto o null")
    return data


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).casefold()


def in_text(value: str, text: str) -> bool:
    """¿Aparece el valor en el texto (ignorando espacios y mayúsculas)?"""
    return _squash(value) in _squash(text)


AMOUNT_FIELDS = {"base_imponible", "iva_importe", "total"}
LINE_NUMERIC = {"cantidad", "precio_unitario", "descuento_pct", "iva_pct", "importe"}


def _strip_unit(raw: str | None) -> str | None:
    """'201,48 EUR' -> '201,48'; '21 %' -> '21'. La unidad no forma parte del valor numérico."""
    return None if raw is None else re.sub(r"\s*(?:EUR|€|%)\s*$", "", raw.strip(), flags=re.IGNORECASE)


def postprocess(data: dict, text: str, verify: bool = True) -> tuple[dict, dict]:
    """Normaliza como la regex y, si verify, descarta valores sin evidencia en el texto.
    En los campos numéricos se verifica el número sin la unidad: el modelo a veces copia la unidad de la
    cabecera de la columna ('8,50 EUR' en una fila que solo contiene '8,50')."""
    result = resultado_vacio()
    descartados = {}

    def check(key: str, raw: str | None, numeric: bool) -> str | None:
        value = _strip_unit(raw) if numeric else raw
        if value is not None and verify and not in_text(value, text):
            descartados[key] = raw
            return None
        return value

    for k in CAMPOS:
        value = check(k, data["campos"].get(k), k in AMOUNT_FIELDS)
        result["campos"][k] = NORMALIZERS.get(k, norm.text)(value)
    for i, line in enumerate(data["lineas"]):
        item = {}
        for k in CAMPOS_LINEA:
            value = check(f"lineas[{i}].{k}", line.get(k), k in LINE_NUMERIC)
            item[k] = norm.amount(value) if k in LINE_NUMERIC else norm.text(value)
        result["lineas"].append(item)
    return result, descartados


def finalize(data: dict | None, text: str, messages: list[dict], attempts: list[dict], seconds: float) -> dict:
    """Resultado final a partir de la respuesta ya validada (o None). Separado de la generación para poder
    reevaluar respuestas guardadas sin volver a llamar al modelo."""
    if data is None:
        result, sin_verificar, descartados = resultado_vacio(), resultado_vacio(), {}
        error = "El LLM no devolvió un JSON válido tras los reintentos."
    else:
        result, descartados = postprocess(data, text, verify=True)
        sin_verificar, _ = postprocess(data, text, verify=False)
        error = None
    return {**result, "error": error, "sin_verificar": sin_verificar, "descartados_sin_evidencia": descartados,
            "traza": {"mensajes": messages, "intentos": attempts}, "tiempo_s": round(seconds, 2)}


def extract_llm(text: str, backend, max_retries: int = 1) -> dict:
    """Devuelve el resultado (verificado), la versión sin verificar y la traza completa (prompt, intentos)."""
    messages = build_messages(text)
    attempts, data = [], None
    t0 = time.perf_counter()
    for _ in range(1 + max_retries):
        t = time.perf_counter()
        raw, usage = backend.generate(messages)
        attempt = {"respuesta": raw, "tiempo_s": round(time.perf_counter() - t, 2), **usage}
        try:
            data = parse_response(raw)
            attempt["valido"] = True
            attempts.append(attempt)
            break
        except (ValueError, json.JSONDecodeError) as e:
            attempt["valido"], attempt["error"] = False, str(e)
            attempts.append(attempt)
            messages = messages + [{"role": "assistant", "content": raw},
                                   {"role": "user", "content": f"La respuesta no es válida ({e}). "
                                                               "Devuelve solo el objeto JSON corregido."}]
    return finalize(data, text, build_messages(text), attempts, time.perf_counter() - t0)
