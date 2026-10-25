# OCR + LLM frente a OCR + regex

Hardware: `{"arquitectura": "aarch64", "cpus": 10, "so": "Linux-7.0.14-linuxkit-aarch64-with-glibc2.41", "ram_total_mb": 7934.1, "ram_disponible_mb": 7355.9, "host": "Apple M5, 16 GB (macOS); Docker Desktop VM linux/arm64", "python": "3.11.17"}`

Texto de entrada: OCR Tesseract (binarizado) de las 5 facturas. 75 campos y 175 celdas por variante.

| Método | Variante | Campos ok | null | error | Celdas líneas | s/doc |
|---|---|---|---|---|---|---|
| ocr+regex | original | 70/75 | 5 | 0 | 175/175 | 0.0 |
| ocr+regex | etiquetas | 15/75 | 60 | 0 | 0/175 | 0.0 |
| ocr+regex | orden | 50/75 | 25 | 0 | 0/175 | 0.0 |
| ocr+regex | ambos | 15/75 | 60 | 0 | 0/175 | 0.0 |
| ocr+llm:qwen2.5-1.5b-q4 | original | 66/75 | 9 | 0 | 147/175 | 20.79 |
| ocr+llm:qwen2.5-1.5b-q4 (sin verificar) | original | 66/75 | 5 | 4 | 147/175 | 20.79 |
| ocr+llm:qwen2.5-1.5b-q4 | etiquetas | 52/75 | 16 | 7 | 175/175 | 27.28 |
| ocr+llm:qwen2.5-1.5b-q4 (sin verificar) | etiquetas | 52/75 | 8 | 15 | 175/175 | 27.28 |
| ocr+llm:qwen2.5-1.5b-q4 | orden | 65/75 | 10 | 0 | 0/175 | 13.26 |
| ocr+llm:qwen2.5-1.5b-q4 (sin verificar) | orden | 65/75 | 5 | 5 | 0/175 | 13.26 |
| ocr+llm:qwen2.5-1.5b-q4 | ambos | 51/75 | 13 | 11 | 124/175 | 23.19 |
| ocr+llm:qwen2.5-1.5b-q4 (sin verificar) | ambos | 51/75 | 5 | 19 | 124/175 | 23.19 |
| ocr+llm:qwen2.5-3b-q4 | original | 70/75 | 5 | 0 | 175/175 | 41.01 |
| ocr+llm:qwen2.5-3b-q4 (sin verificar) | original | 70/75 | 5 | 0 | 175/175 | 41.01 |
| ocr+llm:qwen2.5-3b-q4 | etiquetas | 70/75 | 5 | 0 | 175/175 | 38.5 |
| ocr+llm:qwen2.5-3b-q4 (sin verificar) | etiquetas | 70/75 | 5 | 0 | 175/175 | 38.5 |
| ocr+llm:qwen2.5-3b-q4 | orden | 70/75 | 5 | 0 | 175/175 | 38.5 |
| ocr+llm:qwen2.5-3b-q4 (sin verificar) | orden | 70/75 | 5 | 0 | 175/175 | 38.5 |
| ocr+llm:qwen2.5-3b-q4 | ambos | 70/75 | 5 | 0 | 175/175 | 37.72 |
| ocr+llm:qwen2.5-3b-q4 (sin verificar) | ambos | 70/75 | 5 | 0 | 175/175 | 37.72 |
| ocr+llm:qwen2.5-1.5b-hf | original | 54/75 | 21 | 0 | 145/175 | 312.04 |
| ocr+llm:qwen2.5-1.5b-hf (sin verificar) | original | 54/75 | 11 | 10 | 145/175 | 312.04 |

## Modelos

### qwen2.5-1.5b-q4
- Config: `{"runtime": "llama.cpp", "llama_cpp_python": "0.3.36", "repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "revision": "91cad51170dc346986eccefdc2dd33a9da36ead9", "archivo": "qwen2.5-1.5b-instruct-q4_k_m.gguf", "model_id": "qwen2.5-1.5b-q4", "cuantizacion": "Q4_K_M", "n_ctx": 4096, "n_threads": 10, "temperature": 0.0, "max_tokens": 1500, "salida": "json_schema (gramática)"}`
- Carga: 2.04 s · RAM (MB): {'inicio': 17.3, 'tras_carga': 2036.1, 'pico': 2232.3}

- original: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 4, "descartados_que_eran_error": 4, "descartados_que_eran_correctos": 0, "tokens_generados": 2595}`
- etiquetas: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 8, "descartados_que_eran_error": 8, "descartados_que_eran_correctos": 0, "tokens_generados": 2789}`
- orden: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 5, "descartados_que_eran_error": 5, "descartados_que_eran_correctos": 0, "tokens_generados": 1178}`
- ambos: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 8, "descartados_que_eran_error": 8, "descartados_que_eran_correctos": 0, "tokens_generados": 2477}`

### qwen2.5-3b-q4
- Config: `{"runtime": "llama.cpp", "llama_cpp_python": "0.3.36", "repo": "Qwen/Qwen2.5-3B-Instruct-GGUF", "revision": "7dabda4d13d513e3e842b20f0d435c732f172cbe", "archivo": "qwen2.5-3b-instruct-q4_k_m.gguf", "model_id": "qwen2.5-3b-q4", "cuantizacion": "Q4_K_M", "n_ctx": 4096, "n_threads": 10, "temperature": 0.0, "max_tokens": 1500, "salida": "json_schema (gramática)"}`
- Carga: 6.14 s · RAM (MB): {'inicio': 17.3, 'tras_carga': 3849.7, 'pico': 4071.3}

- original: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 0, "descartados_que_eran_error": 0, "descartados_que_eran_correctos": 0, "tokens_generados": 2879}`
- etiquetas: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 0, "descartados_que_eran_error": 0, "descartados_que_eran_correctos": 0, "tokens_generados": 2854}`
- orden: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 0, "descartados_que_eran_error": 0, "descartados_que_eran_correctos": 0, "tokens_generados": 2884}`
- ambos: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 0, "descartados_que_eran_error": 0, "descartados_que_eran_correctos": 0, "tokens_generados": 2864}`

### qwen2.5-1.5b-hf
- Config: `{"runtime": "transformers", "transformers": "5.20.2", "torch": "2.13.0+cpu", "repo": "Qwen/Qwen2.5-1.5B-Instruct", "revision": "989aa7980e4cf806f80c7fef2b1adb7bc71aa306", "model_id": "qwen2.5-1.5b-hf", "cuantizacion": "ninguna (float32)", "torch_threads": 10, "do_sample": false, "max_new_tokens": 1500, "salida": "texto libre + validación"}`
- Carga: 12.95 s · RAM (MB): {'inicio': 17.3, 'tras_carga': 5776.1, 'pico': 7272.2}

- original: `{"json_valido_1er_intento": 5, "reintentos": 0, "fallos_formato": 0, "descartados": 20, "descartados_que_eran_error": 10, "descartados_que_eran_correctos": 10, "tokens_generados": 3218}`

