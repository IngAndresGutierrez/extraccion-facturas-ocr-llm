# Imagen única para todo el proyecto, ejecución solo en CPU.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MODELS_DIR=/models \
    DOCTR_CACHE_DIR=/models/doctr

WORKDIR /app

# OCR Tesseract (Debian 13: tesseract 5.x) con el modelo de español.
# libgl/libglib: requeridas por OpenCV (EasyOCR y docTR).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# PyTorch en su propia capa (es la más pesada y la que menos cambia).
# Índice CPU: evita descargar CUDA (~2 GB menos).
RUN pip install torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cpu

# Dependencias del proyecto, con versiones fijadas.
RUN pip install \
    pymupdf==2.0 \
    pillow==12.0.0 \
    pytesseract==0.3.13 \
    easyocr==1.7.2 \
    python-doctr==1.1.0 \
    psutil==7.1.0 \
    pytest==9.1.1

# Pesos de los OCR neuronales descargados en la construcción (versión fija dentro de la imagen).
RUN python -c "import easyocr; easyocr.Reader(['es'], gpu=False, model_storage_directory='/models/easyocr', verbose=False)" \
    && python -c "from doctr.models import ocr_predictor; ocr_predictor(pretrained=True)" \
    && ls -R /models

COPY src/ src/
COPY tests/ tests/
COPY pdfs/ pdfs/
COPY evaluacion/ evaluacion/

CMD ["python", "-m", "src.run_text_regex"]
