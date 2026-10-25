"""Variantes del texto OCR para comprobar la robustez ante cambios de etiquetas y de orden.

Se aplican de forma automática y reproducible sobre el texto OCR guardado (no se edita a mano).
- etiquetas: sinónimos habituales en facturas españolas. Algunos los conoce la regex (Divisa, NIF,
  "Su pedido", "Importe total") y otros no, a propósito.
- orden: cada celda en su propia línea (columnas separadas por 2+ espacios -> salto de línea).
  Es el orden que da PyMuPDF sin sort=True o un OCR que lee por bloques: emisor y cliente intercalados
  y las filas de la tabla partidas en una celda por línea.
- ambos: etiquetas + orden.
"""
import re

LABELS = [  # (patrón, sustituto) — el patrón ancla la etiqueta para no tocar valores
    (r"N[úu]mero de factura:", "Nº Fra.:"),
    (r"Fecha de emisi[óo]n:", "Fecha expedición:"),
    (r"Fecha de vencimiento:", "Vence el:"),
    (r"\bMoneda:", "Divisa:"),
    (r"(?<![a-z] )\bPedido:", "Su pedido:"),
    (r"\bEMISOR\b", "PROVEEDOR"),
    (r"\bCLIENTE\b", "DESTINATARIO"),
    (r"\bID fiscal:", "NIF:"),
    (r"\bEmail:", "Correo electrónico:"),
    (r"(?m)^(\s*)Referencia(\s+)Descripci[óo]n", r"\1Código\2Artículo"),
    (r"Forma de pago:", "Modo de pago:"),
    (r"IBAN de prueba:", "Cuenta (IBAN):"),
    (r"Base imponible", "Base de cálculo"),
    (r"IVA \(21 ?%\)", "Cuota IVA 21%"),
    (r"\bTOTAL\b", "Importe total"),
]


def relabel(text: str) -> str:
    for pattern, repl in LABELS:
        text = re.sub(pattern, repl, text)
    return text


def reorder(text: str) -> str:
    return "\n".join(c for line in text.splitlines() for c in re.split(r"\s{2,}", line.strip())) + "\n"


VARIANTS = {
    "original": lambda t: t,
    "etiquetas": relabel,
    "orden": reorder,
    "ambos": lambda t: reorder(relabel(t)),
}
