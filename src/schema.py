"""Esquema de campos a extraer (15 campos de cabecera/resumen + líneas de producto).

Convenciones de formato (comunes a regex, OCR y LLM):
- Fechas: "AAAA-MM-DD" (ISO 8601).
- Importes y números: cadena con punto decimal y sin separador de miles ("1234.50").
- Textos: tal como aparecen, sin espacios sobrantes.
- null si el campo no aparece, es ilegible o es ambiguo. "0.00" es un valor distinto de null.
"""

CAMPOS = {
    # Factura y fechas
    "numero_factura":    {"grupo": "Factura y fechas", "formato": "texto",      "descripcion": "Identificador de la factura (p. ej. PR-2026-001)"},
    "fecha_emision":     {"grupo": "Factura y fechas", "formato": "AAAA-MM-DD", "descripcion": "Fecha en que se emite la factura"},
    "fecha_vencimiento": {"grupo": "Factura y fechas", "formato": "AAAA-MM-DD", "descripcion": "Fecha límite de pago"},
    "moneda":            {"grupo": "Factura y fechas", "formato": "ISO 4217",   "descripcion": "Código de moneda de los importes (p. ej. EUR)"},
    # Pedido y albarán
    "numero_pedido":     {"grupo": "Pedido y albarán", "formato": "texto",      "descripcion": "Número del pedido asociado"},
    # Emisor y cliente
    "emisor_nombre":     {"grupo": "Emisor y cliente", "formato": "texto",      "descripcion": "Razón social de quien emite la factura"},
    "emisor_id_fiscal":  {"grupo": "Emisor y cliente", "formato": "texto",      "descripcion": "Identificador fiscal del emisor"},
    "cliente_nombre":    {"grupo": "Emisor y cliente", "formato": "texto",      "descripcion": "Razón social del cliente"},
    "cliente_id_fiscal": {"grupo": "Emisor y cliente", "formato": "texto",      "descripcion": "Identificador fiscal del cliente"},
    # Contacto
    "cliente_email":     {"grupo": "Contacto",         "formato": "email",      "descripcion": "Correo electrónico del cliente"},
    # Pago y entrega
    "forma_pago":        {"grupo": "Pago y entrega",   "formato": "texto",      "descripcion": "Medio de pago (Transferencia, Tarjeta...)"},
    "iban":              {"grupo": "Pago y entrega",   "formato": "IBAN sin espacios", "descripcion": "IBAN de prueba para el pago"},
    # Importes
    "base_imponible":    {"grupo": "Importes",         "formato": "decimal",    "descripcion": "Base imponible tras descuentos y portes"},
    "iva_importe":       {"grupo": "Importes",         "formato": "decimal",    "descripcion": "Cuota de IVA del resumen"},
    "total":             {"grupo": "Importes",         "formato": "decimal",    "descripcion": "Total a pagar"},
}

# Ampliación: cada elemento de "lineas" tiene estas claves.
CAMPOS_LINEA = {
    "referencia":      "texto",
    "descripcion":     "texto",
    "cantidad":        "decimal",
    "precio_unitario": "decimal",
    "descuento_pct":   "decimal",
    "iva_pct":         "decimal",
    "importe":         "decimal",
}


def resultado_vacio() -> dict:
    """JSON con todas las claves a null; los extractores solo rellenan lo que encuentran."""
    return {"campos": {k: None for k in CAMPOS}, "lineas": []}
