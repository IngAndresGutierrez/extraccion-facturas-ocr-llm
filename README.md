# Extracción de campos de facturas PDF (CPU)

## Estructura
```
src/        schema.py (15 campos + líneas), pdf_text.py (PyMuPDF), regex_extractor.py, normalize.py,
            render.py + ocr.py (Parte 2), evaluate.py, run_text_regex.py / run_ocr_regex.py / benchmark_ocr.py
pdfs/       las cinco facturas
evaluacion/ gold/: referencia transcrita a mano (15 campos + 5 líneas por factura)
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

## Paso 5 · Elección del OCR para CPU
```bash
docker compose run --rm -e HOST_INFO="<CPU y RAM del equipo>" app python -m src.benchmark_ocr
```
Resultados completos, con el detalle por documento y los errores, en `resultados/benchmark_ocr/resumen.md`
y `resumen.json`. Los textos de cada motor están en `resultados/benchmark_ocr/<motor>_<pre>/`.

**Metodología**
- Cada motor procesa las 5 facturas renderizadas a 250 DPI: las 2 escaneadas y las 3 de texto como imagen, sin
  usar su capa de texto. Después se aplican las mismas regex.
- La salida se compara con `evaluacion/gold/`, la referencia transcrita a mano. El gold de 01–03 coincide
  exactamente con la salida independiente de la Parte 1.
- Por campo se distinguen tres resultados: **ok**, **null** (se ve y se revisa) y **error** (un valor incorrecto
  que parece válido, el caso más grave). En las líneas de producto se cuentan las celdas correctas (175).
- Cada motor se ejecuta en un proceso nuevo. La RAM es el pico de RSS del proceso más sus hijos (el binario
  de tesseract), muestreado cada 20 ms. La carga es el tiempo de instanciar el motor con los pesos ya en disco.

**Equipo**: Apple M5, 16 GB (macOS). Docker Desktop corre una VM linux/arm64 con 10 CPU y 7,9 GB de RAM
(unos 7,0 GB disponibles). Python 3.11.17 y PyTorch 2.13.0+cpu con 10 hilos.

| Motor | Modelos / configuración | Preproc. | Carga | s/doc | RAM pico | Campos ok | null | error | Celdas líneas |
|---|---|---|---|---|---|---|---|---|---|
| Tesseract 5 | `spa` (tessdata Debian), `--oem 1 --psm 3` | ninguno | 0 s | 0,76 | 314 MB | 65/75 | 10 | 0 | 175/175 |
| **Tesseract 5** | ídem | **binarizar** | **0 s** | **0,64** | **273 MB** | **70/75** | 5 | **0** | **175/175** |
| EasyOCR 1.7.2 | CRAFT `craft_mlt_25k` + CRNN `latin_g2`, `es` | ninguno | 2,3 s | 16,7 | 5447 MB | 68/75 | 6 | 1 | 70/175 |
| EasyOCR 1.7.2 | ídem | binarizar | 2,4 s | 16,5 | 5451 MB | 66/75 | 7 | 2 | 28/175 |
| docTR 1.1.0 | `fast_base` + `crnn_vgg16_bn` (oficiales) | ninguno | 2,6 s | 3,61 | 1547 MB | 64/75 | 5 | 6 | 173/175 |
| docTR 1.1.0 | ídem | binarizar | 2,4 s | 3,61 | 1582 MB | 64/75 | 5 | 6 | 173/175 |

**Elección: Tesseract 5 con binarización.**
- Es el más preciso: 70/75 campos y 175/175 celdas.
- No produce ningún valor incorrecto. Su único fallo es sistemático y visible: no lee la `@`, así que
  `cliente_email` queda en null.
- Es el más rápido (0,64 s por documento) y el más ligero (unos 270 MB en total, de los que el binario de
  tesseract ocupa 56–97 MB). No tiene tiempo de carga.

**Descartados**
- **EasyOCR**: es 26 veces más lento y ocupa 20 veces más RAM. Su pico de 5,4 GB se acerca al total de la VM:
  el detector CRAFT trabaja sobre la página entera, de hasta 2560 px. Además pierde los dígitos aislados de la
  tabla (70/175 celdas) y produce emails incorrectos (`clienteol`, `clienteos`). Sí lee bien acentos y `@`.
- **docTR**: es rápido para ser una red neuronal (3,6 s) y lee bien la tabla y los emails. Pero el vocabulario de
  todos sus reconocedores oficiales (126 caracteres, francés) no tiene á, í, ó, ú ni ñ. Por eso da 6 valores
  incorrectos sin aviso (`Papeleria`, `Domiciliacion`, `Prâcticas`): un fallo estructural que no se resuelve con
  preprocesado. Un modelo multilingüe de la comunidad podría corregirlo, pero no es oficial y no lo hemos probado.

**Limitaciones**
- Son solo 5 documentos con la misma plantilla y 2 escaneos limpios generados digitalmente, sin ruido, inclinación
  ni arrugas. Con escaneos reales el orden entre motores podría cambiar.
- El umbral de binarización (170) se ajustó con estas mismas facturas, así que el resultado de Tesseract es
  optimista.
- Los tiempos varían de una ejecución a otra: EasyOCR dio entre 13,9 y 16,7 s por documento en dos ejecuciones.
  Se midieron dentro de la VM de Docker, no directamente sobre el macOS del equipo.

## Parte adicional · OCR + LLM local
```bash
docker compose run --rm app python -m src.download_models qwen2.5-3b-q4        # ≈ 2 GB en modelos/
docker compose run --rm -e HOST_INFO="<CPU y RAM>" app python -m src.benchmark_llm
docker compose run --rm app python -m src.benchmark_llm --models qwen2.5-1.5b-hf --variants original
docker compose run --rm app python -m src.benchmark_llm --reevaluar    # recalcula desde las respuestas guardadas
```
Los pesos no van en el repositorio ni en la imagen. `src/download_models.py` descarga cada modelo de Hugging Face con
la revisión (commit) fijada.

**Cómo funciona** (`src/llm_extractor.py`)
1. El LLM recibe el **mismo texto OCR guardado** (`resultados/benchmark_ocr/tesseract_binarize/*.txt`), sin imágenes
   ni respuestas correctas. El prompt completo está en `resultados/llm/prompt.txt`. Define los 15 campos y las
   líneas, pide copiar cada valor literalmente y exige `null` si no hay evidencia o hay ambigüedad.
2. llama.cpp restringe la salida con una gramática generada desde el esquema JSON, así que el formato siempre es
   válido. Aun así se valida (claves exactas, string o null). Si falla, hay un reintento que incluye el error.
   Cada JSON guarda el prompt, la respuesta original y todos los intentos.
3. La normalización (fechas, importes, IBAN, formato de email y de moneda) la hace `normalize.py`, igual que con
   la regex, no el modelo.
4. **Verificación de evidencia**: todo valor que no aparece en el texto del OCR se descarta (null). En los números
   se verifica la cifra sin unidad, porque el modelo copia «EUR» de la cabecera «Precio EUR».

**Robustez** (`src/perturb.py`): sobre el mismo texto OCR se generan variantes automáticas.
- **etiquetas**: «Nº Fra.», «Vence el», «PROVEEDOR/DESTINATARIO», «NIF», «Modo de pago», «Base de cálculo»,
  «Cuota IVA 21%»… La regex conoce algunos sinónimos y otros no.
- **orden**: cada celda en su propia línea, como PyMuPDF sin `sort`, con emisor y cliente intercalados.
- **ambos**: las dos variantes juntas.

**Resultados** (5 facturas; 75 campos y 175 celdas por variante; `resultados/llm/resumen.md`)

| Método | Variante | Campos ok | null | error | Celdas | s/doc |
|---|---|---|---|---|---|---|
| OCR + regex | original | 70 | 5 | 0 | 175 | < 0,01 |
| OCR + regex | etiquetas | 15 | 60 | 0 | 0 | < 0,01 |
| OCR + regex | orden | 50 | 25 | 0 | 0 | < 0,01 |
| OCR + regex | ambos | 15 | 60 | 0 | 0 | < 0,01 |
| **Qwen2.5-3B Q4_K_M** | original | **70** | 5 | **0** | **175** | 41 |
| **Qwen2.5-3B Q4_K_M** | etiquetas | **70** | 5 | **0** | **175** | 38 |
| **Qwen2.5-3B Q4_K_M** | orden | **70** | 5 | **0** | **175** | 38 |
| **Qwen2.5-3B Q4_K_M** | ambos | **70** | 5 | **0** | **175** | 38 |
| Qwen2.5-1.5B Q4_K_M | original | 66 | 9 | 0 | 147 | 21 |
| Qwen2.5-1.5B Q4_K_M | etiquetas | 52 | 16 | 7 | 175 | 27 |
| Qwen2.5-1.5B Q4_K_M | orden | 65 | 10 | 0 | 0 | 13 |
| Qwen2.5-1.5B Q4_K_M | ambos | 51 | 13 | 11 | 124 | 23 |
| Qwen2.5-1.5B float32 (transformers) | original | 54 | 21 | 0 | 145 | 312 |

| Modelo | Runtime | Carga | RAM tras carga | RAM pico | JSON válido al 1.er intento |
|---|---|---|---|---|---|
| Qwen2.5-3B-Instruct Q4_K_M | llama.cpp 0.3.36 | 6,1 s | 3,8 GB | 4,1 GB | 20/20 |
| Qwen2.5-1.5B-Instruct Q4_K_M | llama.cpp 0.3.36 | 2,0 s | 2,0 GB | 2,2 GB | 20/20 |
| Qwen2.5-1.5B-Instruct float32 | transformers 5.20.2 + torch 2.13.0 | 13 s | 5,8 GB | 7,3 GB | 5/5 |

**Elección: `Qwen/Qwen2.5-3B-Instruct-GGUF`, archivo `qwen2.5-3b-instruct-q4_k_m.gguf`**
- Revisión `7dabda4d13d513e3e842b20f0d435c732f172cbe`, cuantización Q4_K_M, runtime llama.cpp (`llama-cpp-python`
  0.3.36). Configuración: `n_ctx=4096`, 10 hilos, `temperature=0`, `seed=0`, `max_tokens=1500` y salida por esquema JSON.
- Es el único modelo **sin ningún valor incorrecto** en las 4 variantes: 70/75 campos y 175/175 celdas. Además
  los acierta todos ya antes de la verificación.
- Sus 5 nulls son siempre `cliente_email`: Tesseract no lee la `@` y el modelo no inventa la dirección.
- Coste: unos 40 s por documento y 4,1 GB de RAM. Cabe en la VM de 7,9 GB, pero no deja sitio para un segundo
  modelo en paralelo.

**Alternativas descartadas**
- **Qwen2.5-1.5B Q4_K_M**: es unas 2 veces más rápido y usa la mitad de RAM, pero con las etiquetas cambiadas toma
  **valores reales del campo equivocado**. Pone el código de cliente `CLI-0301` como ID fiscal y el subtotal sin
  descuentos como base imponible. Esos valores sí aparecen en el texto, así que la verificación no los detecta
  (7 y 11 errores que llegan al resultado). Las variantes estropeadas (`DEM-003`, IBAN truncado) sí las atrapa.
  Con «orden» devuelve la tabla vacía.
- **Qwen2.5-1.5B en PyTorch/transformers sin cuantizar**: es el mismo modelo y peor en todo. Tarda 312 s por
  documento (15 veces más), su pico de 7,3 GB está al límite de la VM, y sin gramática produce más valores
  inválidos (10 errores antes de verificar, 21 null después). La cuantización y llama.cpp son lo que hace viable
  un LLM en CPU.

**¿Compensa el LLM?**
- Con la plantilla conocida, no: la regex consigue lo mismo (70/75, 175/175) en milisegundos y sin 4 GB de RAM.
- Cuando cambian las etiquetas o el orden, la regex se queda en 15–50 campos y 0 celdas, mientras que el 3B mantiene
  70/75 y 175/175. Su valor está en documentos con un formato desconocido. Una opción razonable es usar la regex por
  defecto y recurrir al LLM cuando la regex devuelve muchos null.
- **Límite de la verificación**: detecta valores inventados o mal copiados, pero no un valor real asignado al campo
  equivocado. Eso exige revisión humana o reglas cruzadas (p. ej. base + IVA = total).
- **Otras limitaciones**: solo 5 documentos de una misma plantilla, y variantes sintéticas generadas por nosotros.
  Con temperatura 0 el resultado es determinista, pero no medimos la varianza con otros prompts.

## Parte 3 · Interfaz web (FastAPI + HTML/CSS/JS)
```bash
docker compose up web          # http://localhost:8000   (Ctrl+C para parar)
```
- `src/api.py` contiene solo las rutas HTTP. La lógica de lectura y extracción está en `src/pipeline.py`, que no
  depende de FastAPI y reutiliza `pdf_text`, `ocr`, `regex_extractor` y `llm_extractor`.
- `frontend/`: `index.html` define los controles, `styles.css` el aspecto y `app.js` envía el PDF con
  `fetch` + `FormData`, consulta el estado y pinta los campos, las líneas, el texto leído y el JSON.

| Ruta | Función |
|---|---|
| `GET /` · `GET /static/*` | página y recursos estáticos |
| `POST /api/extract` | `file` (PDF) + `method` (`texto_regex` · `ocr_regex` · `ocr_llm`) → `202 {"job_id"}` |
| `GET /api/jobs/{id}` | `en_cola` · `procesando` (+ etapa y segundos) · `completado` (+ resultado) · `error` (+ mensaje) |
| `GET /api/jobs/{id}/descarga` | JSON del resultado como archivo adjunto |

OCR + LLM tarda unos 40 s, así que se usa el flujo con identificador de trabajo que permite el enunciado. Los
trabajos se ejecutan en segundo plano y de uno en uno: son tareas de CPU y en paralelo solo competirían. El estado
se guarda en memoria, sin base de datos ni cola. Las entradas inválidas (no es PDF, archivo vacío, más de 20 MB,
método desconocido) se rechazan con un 400/413 inmediato. Los fallos durante el proceso (PDF dañado, método de
texto sobre un escaneo, modelo sin descargar) terminan el trabajo en `error` con un mensaje que explica qué hacer.
Las evidencias de cada trabajo (texto leído, salida del OCR, traza del LLM y JSON) se guardan en `resultados/web/<id>/`.

**Verificación desde la interfaz** (navegador real con Playwright; capturas en `resultados/web/capturas/`):

| Caso | Resultado |
|---|---|
| `Factura_01_texto.pdf` · texto + regex | 15/15 campos, 5 líneas, 0,02 s |
| `Factura_04_imagen.pdf` · OCR + regex | 14/15 campos (email null), 5 líneas, 0,8 s |
| `Factura_05_imagen.pdf` · OCR + LLM | 14/15 campos, 5 líneas, 37 s (incluye la carga del modelo); contenedor ≈ 4,3 GB |
| Error: `Factura_04_imagen.pdf` · texto + regex | «Este PDF no tiene texto seleccionable… Elige OCR + regex u OCR + LLM» |
| Error: `notas.txt` | «notas.txt no es un PDF válido (falta la cabecera %PDF)» |

Tests automáticos de la API en `tests/test_api.py`: el LLM se sustituye por uno simulado y se comprueba que un
valor inventado se descarta.
