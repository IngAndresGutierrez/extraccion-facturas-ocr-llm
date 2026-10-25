# Imagen única para todo el proyecto, ejecución solo en CPU.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# OCR Tesseract (Debian 13: tesseract 5.x) con el modelo de español.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# PyTorch en su propia capa (es la más pesada y la que menos cambia).
# Índice CPU: evita descargar CUDA (~2 GB menos).
RUN pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu

# Dependencias del proyecto, con versiones fijadas.
RUN pip install \
    pymupdf==2.0 \
    pillow==12.0.0 \
    pytesseract==0.3.13 \
    pytest==9.1.1

COPY src/ src/
COPY tests/ tests/
COPY pdfs/ pdfs/

CMD ["python", "-m", "src.run_text_regex"]
