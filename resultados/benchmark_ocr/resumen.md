# Benchmark OCR (CPU)

Hardware: `{"arquitectura": "aarch64", "cpus": 10, "so": "Linux-7.0.14-linuxkit-aarch64-with-glibc2.41", "ram_total_mb": 7934.1, "ram_disponible_mb": 7108.9, "host": "Apple M5, 16 GB (macOS); Docker Desktop VM linux/arm64", "python": "3.11.17"}`

5 facturas renderizadas a 250 DPI; 15 campos por factura (75) y 35 celdas de líneas por factura (175).

| Motor | Preproc. | Carga (s) | s/doc (media) | RAM pico (MB) | Campos ok | null | error | Celdas líneas |
|---|---|---|---|---|---|---|---|---|
| tesseract | none | 0.0 | 0.76 | 313.8 | 65/75 | 10 | 0 | 175/175 |
| tesseract | binarize | 0.0 | 0.64 | 272.5 | 70/75 | 5 | 0 | 175/175 |
| easyocr | none | 2.26 | 16.68 | 5446.6 | 68/75 | 6 | 1 | 70/175 |
| easyocr | binarize | 2.43 | 16.54 | 5450.9 | 66/75 | 7 | 2 | 28/175 |
| doctr | none | 2.6 | 3.61 | 1546.5 | 64/75 | 5 | 6 | 173/175 |
| doctr | binarize | 2.38 | 3.61 | 1581.9 | 64/75 | 5 | 6 | 173/175 |

## Detalle por documento

### tesseract · none
`{"engine": "tesseract", "version": "5.5.0", "lang": "spa", "psm": 3, "oem": 1, "preprocesado": "none", "dpi": 250}`

- Factura_01_texto: 13/15 ok, 0.8 s, celdas 35/35, null: cliente_email, iban
- Factura_02_texto: 13/15 ok, 0.78 s, celdas 35/35, null: cliente_email, iban
- Factura_03_texto: 13/15 ok, 0.74 s, celdas 35/35, null: cliente_email, iban
- Factura_04_imagen: 13/15 ok, 0.74 s, celdas 35/35, null: cliente_email, iban
- Factura_05_imagen: 13/15 ok, 0.76 s, celdas 35/35, null: cliente_email, iban

### tesseract · binarize
`{"engine": "tesseract", "version": "5.5.0", "lang": "spa", "psm": 3, "oem": 1, "preprocesado": "binarize", "dpi": 250}`

- Factura_01_texto: 14/15 ok, 0.66 s, celdas 35/35, null: cliente_email
- Factura_02_texto: 14/15 ok, 0.63 s, celdas 35/35, null: cliente_email
- Factura_03_texto: 14/15 ok, 0.62 s, celdas 35/35, null: cliente_email
- Factura_04_imagen: 14/15 ok, 0.65 s, celdas 35/35, null: cliente_email
- Factura_05_imagen: 14/15 ok, 0.64 s, celdas 35/35, null: cliente_email

### easyocr · none
`{"engine": "easyocr", "version": "1.7.2", "torch": "2.13.0+cpu", "lang": "es", "detector": "craft_mlt_25k", "recognizer": "latin_g2", "preprocesado": "none", "dpi": 250}`

- Factura_01_texto: 13/15 ok, 17.15 s, celdas 14/35, null: iban, **error**: cliente_email: 'compras@clienteol.example' ≠ 'compras@cliente01.example'
- Factura_02_texto: 13/15 ok, 16.56 s, celdas 14/35, null: cliente_email, iban
- Factura_03_texto: 14/15 ok, 16.85 s, celdas 14/35, null: iban
- Factura_04_imagen: 14/15 ok, 16.22 s, celdas 14/35, null: iban
- Factura_05_imagen: 14/15 ok, 16.63 s, celdas 14/35, null: iban

### easyocr · binarize
`{"engine": "easyocr", "version": "1.7.2", "torch": "2.13.0+cpu", "lang": "es", "detector": "craft_mlt_25k", "recognizer": "latin_g2", "preprocesado": "binarize", "dpi": 250}`

- Factura_01_texto: 13/15 ok, 16.55 s, celdas 7/35, null: cliente_email, iban
- Factura_02_texto: 13/15 ok, 16.58 s, celdas 7/35, null: cliente_email, iban
- Factura_03_texto: 13/15 ok, 16.26 s, celdas 7/35, null: iban, **error**: cliente_email: 'compras@clienteo03.example' ≠ 'compras@cliente03.example'
- Factura_04_imagen: 14/15 ok, 16.62 s, celdas 7/35, null: iban
- Factura_05_imagen: 13/15 ok, 16.7 s, celdas 0/35, null: iban, **error**: cliente_email: 'compras@clienteos.example' ≠ 'compras@cliente05.example'

### doctr · none
`{"engine": "doctr", "version": "v1.1.0", "torch": "2.13.0+cpu", "detector": "fast_base", "recognizer": "crnn_vgg16_bn", "vocab": "126 caracteres (francés)", "preprocesado": "none", "dpi": 250}`

- Factura_01_texto: 13/15 ok, 3.34 s, celdas 34/35, null: iban, **error**: emisor_nombre: 'Papeleria Aula Demo' ≠ 'Papelería Aula Demo'
- Factura_02_texto: 14/15 ok, 3.72 s, celdas 35/35, null: iban
- Factura_03_texto: 13/15 ok, 3.62 s, celdas 34/35, null: iban, **error**: cliente_nombre: 'Aula de Formacion Ejemplo' ≠ 'Aula de Formación Ejemplo'
- Factura_04_imagen: 12/15 ok, 3.63 s, celdas 35/35, null: iban, **error**: emisor_nombre: 'Papeleria Taller Demo' ≠ 'Papelería Taller Demo'; forma_pago: 'Domiciliacion' ≠ 'Domiciliación'
- Factura_05_imagen: 12/15 ok, 3.76 s, celdas 35/35, null: iban, **error**: emisor_nombre: 'Oficina Didactica Demo' ≠ 'Oficina Didáctica Demo'; cliente_nombre: 'Instituto de Prâcticas Ejemplo' ≠ 'Instituto de Prácticas Ejemplo'

### doctr · binarize
`{"engine": "doctr", "version": "v1.1.0", "torch": "2.13.0+cpu", "detector": "fast_base", "recognizer": "crnn_vgg16_bn", "vocab": "126 caracteres (francés)", "preprocesado": "binarize", "dpi": 250}`

- Factura_01_texto: 13/15 ok, 3.34 s, celdas 34/35, null: iban, **error**: emisor_nombre: 'Papeleria Aula Demo' ≠ 'Papelería Aula Demo'
- Factura_02_texto: 14/15 ok, 3.72 s, celdas 35/35, null: iban
- Factura_03_texto: 13/15 ok, 3.64 s, celdas 34/35, null: iban, **error**: cliente_nombre: 'Aula de Formacion Ejemplo' ≠ 'Aula de Formación Ejemplo'
- Factura_04_imagen: 12/15 ok, 3.67 s, celdas 35/35, null: iban, **error**: emisor_nombre: 'Papeleria Taller Demo' ≠ 'Papelería Taller Demo'; forma_pago: 'Domiciliacion' ≠ 'Domiciliación'
- Factura_05_imagen: 12/15 ok, 3.69 s, celdas 35/35, null: iban, **error**: emisor_nombre: 'Oficina Didactica Demo' ≠ 'Oficina Didáctica Demo'; cliente_nombre: 'Instituto de Prâcticas Ejemplo' ≠ 'Instituto de Prácticas Ejemplo'
