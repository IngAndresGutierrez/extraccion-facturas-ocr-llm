"""Extracción de campos con regex + reglas de contexto.

Entrada: texto "con disposición" (una línea visual por línea, columnas separadas por 2+ espacios),
como el que da PyMuPDF con sort=True. La misma función se reutilizará sobre el texto del OCR.

Principios:
- Se busca el valor junto a su etiqueta, nunca "el primer número/fecha" del documento.
- Si una etiqueta aparece con varios valores distintos -> ambiguo -> null.
- La búsqueda devuelve el texto bruto; la normalización va en normalize.py.
"""
import re

from . import normalize as norm
from .schema import resultado_vacio

# Un valor "de celda": termina en fin de línea o donde empieza otra columna (2+ espacios).
CELL = r"([^\n]+?)(?=\s{2,}|\s*$)"
TOKEN = r"([A-Z0-9][A-Z0-9/\-.]*\d[A-Z0-9/\-.]*)"     # identificador con al menos un dígito
DATE = r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})"
AMOUNT = r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})"
SEP = r"\s*[:#]?\s*"
FLAGS = re.MULTILINE

# Etiquetas: (?i:...) hace insensible a mayúsculas solo la etiqueta, no el valor capturado.
PATTERNS = {
    "numero_factura": rf"(?i:n[úu]mero\s+de\s+factura|n\.?\s*[º°o]\.?\s*(?:de\s+)?factura|factura\s+n\.?\s*[º°o]\.?){SEP}{TOKEN}",
    "fecha_emision": rf"(?i:fecha\s+de\s+emisi[óo]n|fecha\s+factura){SEP}{DATE}",
    "fecha_vencimiento": rf"(?i:fecha\s+de\s+vencimiento|vencimiento){SEP}{DATE}",
    "moneda": rf"(?i:moneda|divisa){SEP}([A-Z]{{3}})\b",
    # "Fecha de pedido: 30/08/2026" no debe tomarse como número de pedido.
    "numero_pedido": rf"(?i:n[úu]mero\s+de\s+pedido|n\.?\s*[º°o]\.?\s*pedido|(?<!de )pedido){SEP}(?![\d/.\-]+\b){TOKEN}",
    "forma_pago": rf"(?i:forma\s+de\s+pago|m[ée]todo\s+de\s+pago){SEP}{CELL}",
    "iban": rf"(?i:iban)(?i:\s+de\s+prueba)?{SEP}([A-Z]{{2}}\d{{2}}(?:[ ]?[A-Z0-9]{{4}}){{2,7}}(?:[ ]?[A-Z0-9]{{1,4}})?)",
    "base_imponible": rf"(?i:base\s+imponible){SEP}{AMOUNT}",
    # "IVA (21 %)" en el resumen; excluye la cabecera de tabla "IVA %" y el texto libre.
    "iva_importe": rf"(?i:(?:cuota\s+de\s+)?IVA)\s*\(\s*\d+(?:,\d+)?\s*%\s*\){SEP}{AMOUNT}",
    # \b evita "Subtotal".
    "total": rf"(?i:\btotal(?:\s+factura|\s+a\s+pagar)?)\b{SEP}{AMOUNT}",
}

NORMALIZERS = {
    "fecha_emision": norm.date_iso,
    "fecha_vencimiento": norm.date_iso,
    "iban": norm.iban,
    "base_imponible": norm.amount,
    "iva_importe": norm.amount,
    "total": norm.amount,
}


def find_unique(pattern: str, text: str) -> str | None:
    """Valor capturado si todas las coincidencias coinciden; None si no hay o hay varias distintas."""
    values = {norm.text(m.group(1)) for m in re.finditer(pattern, text, FLAGS)}
    values.discard(None)
    return values.pop() if len(values) == 1 else None


# ---------------------------------------------------------------- emisor / cliente

PARTY_HEADER = re.compile(r"^\s*EMISOR\s{2,}CLIENTE\s*$", re.MULTILINE | re.IGNORECASE)
TABLE_HEADER = re.compile(r"^\s*Referencia\s+Descripci[óo]n", re.MULTILINE | re.IGNORECASE)


def _party_columns(text: str) -> list[tuple[str, str]] | None:
    """Líneas del bloque emisor/cliente divididas en (izquierda, derecha).
    La columna izquierda es el emisor y la derecha el cliente (orden de las cabeceras)."""
    start = PARTY_HEADER.search(text)
    if not start:
        return None
    end = TABLE_HEADER.search(text, start.end())
    block = text[start.end(): end.start() if end else None]
    rows = []
    for line in block.splitlines():
        if not line.strip():
            continue
        cols = re.split(r"\s{2,}", line.strip())
        # Una línea con una sola columna no se puede atribuir con seguridad.
        rows.append((cols[0], cols[1]) if len(cols) == 2 else (None, None))
    return rows


def _labeled(rows, label: str, value_re: str = r"(.+)") -> tuple[str | None, str | None]:
    pattern = re.compile(rf"(?i:{label}){SEP}{value_re}")
    found = [(pattern.fullmatch(l or ""), pattern.fullmatch(r or "")) for l, r in rows]
    found = [(l, r) for l, r in found if l or r]
    if len(found) != 1:
        return None, None
    l, r = found[0]
    return (norm.text(l.group(1)) if l else None, norm.text(r.group(1)) if r else None)


def extract_parties(text: str) -> dict:
    out = dict.fromkeys(["emisor_nombre", "emisor_id_fiscal", "cliente_nombre",
                         "cliente_id_fiscal", "cliente_email"])
    rows = _party_columns(text)
    if not rows:
        return out
    # El nombre es la primera fila del bloque y no lleva etiqueta "X:".
    first_l, first_r = rows[0]
    if first_l and first_r and ":" not in first_l + first_r:
        out["emisor_nombre"], out["cliente_nombre"] = norm.text(first_l), norm.text(first_r)
    out["emisor_id_fiscal"], out["cliente_id_fiscal"] = _labeled(rows, r"id\s+fiscal|nif|cif", r"(\S+)")
    _, out["cliente_email"] = _labeled(rows, r"e-?mail|correo", r"([\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+)")
    return out


# ---------------------------------------------------------------- líneas de producto

LINE_ITEM = re.compile(
    r"^\s*(?P<referencia>[A-Z]{2,}-\d+)\s+(?P<descripcion>\S.*?)\s{2,}"
    r"(?P<cantidad>\d+(?:,\d+)?)\s+(?P<precio_unitario>\d+(?:\.\d{3})*,\d{2})\s+"
    r"(?P<descuento_pct>\d+(?:,\d+)?)\s+(?P<iva_pct>\d+(?:,\d+)?)\s+"
    r"(?P<importe>\d+(?:\.\d{3})*,\d{2})\s*$",
    re.MULTILINE,
)
NUMERIC_LINE_FIELDS = ("cantidad", "precio_unitario", "descuento_pct", "iva_pct", "importe")


def extract_lines(text: str) -> list[dict]:
    header = TABLE_HEADER.search(text)
    if not header:
        return []
    items = []
    for m in LINE_ITEM.finditer(text, header.end()):
        item = {k: norm.text(v) for k, v in m.groupdict().items()}
        for k in NUMERIC_LINE_FIELDS:
            item[k] = norm.amount(item[k])
        items.append(item)
    return items


# ---------------------------------------------------------------- API

def extract(text: str) -> dict:
    result = resultado_vacio()
    campos = result["campos"]
    for field, pattern in PATTERNS.items():
        raw = find_unique(pattern, text)
        campos[field] = NORMALIZERS.get(field, norm.text)(raw)
    campos.update(extract_parties(text))
    result["lineas"] = extract_lines(text)
    return result
