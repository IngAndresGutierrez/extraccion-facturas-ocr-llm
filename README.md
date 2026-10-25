# Extracción de campos de facturas PDF (CPU)

## Estructura
```
src/        schema.py (15 campos + líneas), pdf_text.py (PyMuPDF), regex_extractor.py, normalize.py,
            run_text_regex.py (Parte 1)
pdfs/       las cinco facturas
resultados/ texto/ (texto leído) · json/texto_regex/ (salida Parte 1)
tests/      pytest
```

## Instalación (solo Docker, CPU)
Todo se ejecuta en un contenedor: Python 3.11 y PyTorch 2.13.0 para CPU, sin CUDA.
Las versiones de las dependencias están fijadas en el `Dockerfile`.
```bash
docker compose build
```
`compose.yaml` monta el proyecto en `/app`. Así, los cambios de código y los `resultados/` se ven en el host
sin reconstruir la imagen.

## Parte 1 · Texto seleccionable + regex
```bash
docker compose run --rm app python -m src.run_text_regex     # procesa pdfs/*.pdf
docker compose run --rm app python -m pytest -q
```

Decisiones:
- Se lee con `page.get_text("text", sort=True)`: conserva la disposición visual (una línea por fila,
  columnas separadas por 2+ espacios). Sin `sort`, PyMuPDF intercala emisor y cliente línea a línea.
- Emisor/cliente: dentro del bloque `EMISOR  CLIENTE`, la columna izquierda es el emisor y la derecha el cliente.
  Si una fila no tiene dos columnas, ese campo queda en `null`, porque no se sabe a quién pertenece.
- Cada campo se busca junto a su etiqueta, con variantes (`Número de factura`, `N.º factura`, `Factura nº`…).
  Si la misma etiqueta aparece con valores distintos, el campo queda en `null` por ambiguo.
- La búsqueda (regex) y la normalización (`normalize.py`) están separadas. Las fechas se guardan como
  `AAAA-MM-DD`, los importes como `"1234.50"` y el IBAN sin espacios.
- Los PDFs sin capa de texto (04 y 05) se detectan y devuelven un error que remite al OCR.
