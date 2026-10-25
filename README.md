# Extracción de campos de facturas PDF (CPU)

## Estructura
```
src/        schema.py (15 campos + líneas), pdf_text.py (PyMuPDF), regex_extractor.py, normalize.py,
            render.py + ocr.py (Parte 2), run_text_regex.py / run_ocr_regex.py (scripts)
pdfs/       las cinco facturas
resultados/ texto/ · imagenes/ · ocr/<motor>/ (salida original + texto reconstruido) · json/<método>/
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

## Parte 2 · PDF escaneado: imagen + OCR + regex
```bash
docker compose run --rm app python -m src.run_ocr_regex                    # pdfs/*_imagen.pdf, Tesseract
docker compose run --rm app python -m src.run_ocr_regex --dpi 300 --pre none pdfs/Factura_04_imagen.pdf
```
Por página guarda la imagen renderizada, la imagen preprocesada que recibe el OCR, la salida original del OCR
(palabras, cajas y confianza en `resultados/ocr/<motor>/*.json`), el texto reconstruido (`*.txt`) y el JSON final.

Configuración (Tesseract 5, `spa`, `--oem 1` LSTM):
- **Render de la página completa a 250 DPI**: es la resolución de la imagen incrustada (2067×2924 px en A4).
  Subir a 300 o 400 DPI no mejoró ningún campo y aumentó el tiempo de 0,6 s a 1,0 s por página.
- **`--psm 3`**: con `psm 11` (texto disperso) se perdían los dígitos aislados de la tabla (cantidades y
  descuentos), así que salían 0 líneas. Con `psm 3` salen las 5 líneas.
- **Binarización (gris + umbral 170)**: sin ella, Tesseract lee `ESOO` en lugar de `ES00` y el IBAN queda en null.
  Con escala de grises, autocontraste o escalado ×2 el error seguía.

Adaptaciones respecto a la Parte 1 (las reglas regex no cambian):
- El OCR devuelve palabras sueltas con su caja, no una disposición. `ocr.layout_text` agrupa las palabras en
  líneas por solapamiento vertical y pone 2 o más espacios cuando el hueco supera unos 2 caracteres. Así se
  obtiene el mismo formato que `get_text(sort=True)` y se reutilizan las reglas de columnas (emisor/cliente)
  y de tabla. Esta reconstrucción no depende del motor de OCR.
- El texto del OCR no se corrige. Tesseract nunca lee la `@` de los emails (`comprasO cliente04.example`),
  así que `cliente_email` queda en `null` en lugar de adivinar el valor.

Resultado con Tesseract: 14/15 campos y 5/5 líneas en las facturas 04 y 05, comprobados contra la imagen.
El único null es `cliente_email`. El proceso tarda unos 0,75 s por documento.
