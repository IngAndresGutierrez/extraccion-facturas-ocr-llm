"""Normalización de valores ya localizados. Separada de la búsqueda (regex) a propósito:
cada función recibe el texto capturado y devuelve el formato acordado o None si no puede.
"""
import re
from datetime import date

_AMOUNT_ES = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d+$|^\d+(?:,\d+)?$")


def amount(raw: str | None) -> str | None:
    """'1.234,50' -> '1234.50'; '21' -> '21'. Solo formato español (coma decimal)."""
    if raw is None:
        return None
    s = re.sub(r"\s+", "", raw)
    if not _AMOUNT_ES.match(s):
        return None
    return s.replace(".", "").replace(",", ".")


def date_iso(raw: str | None) -> str | None:
    """'01/09/2026' (también con '-' o '.') -> '2026-09-01'. Años de 2 cifras -> None (ambiguo)."""
    if raw is None:
        return None
    m = re.fullmatch(r"\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\s*", raw)
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def iban(raw: str | None) -> str | None:
    """Quita espacios y valida forma (país + control + 11..30 alfanuméricos).
    No se comprueba el dígito de control: los IBAN de la práctica son de prueba."""
    if raw is None:
        return None
    s = re.sub(r"\s+", "", raw).upper()
    return s if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s) else None


def text(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = re.sub(r"\s+", " ", raw).strip(" :·-")
    return s or None
