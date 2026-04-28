# Dockerfile para Recycling Net 11

# ETAPA 1: Base (descargar modelo una vez)
FROM python:3.10-slim as base

# Establecer variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HUGGINGFACE_HUB_CACHE=/app/.cache/huggingface

# Instalar herramientas del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de app
WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Predescargar modelo (esto es IMPORTANTE para cold start)
RUN python -c "from transformers import pipeline; \
    pipeline('image-classification', \
    model='prithivMLmods/Recycling-Net-11')"

# ETAPA 2: Runtime (la imagen final)
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HUGGINGFACE_HUB_CACHE=/app/.cache/huggingface

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar solo lo necesario de la etapa anterior
COPY --from=base /app/.cache /app/.cache
COPY --from=base /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

# Copiar código
COPY app.py .
COPY config.py .
COPY utils.py .

# Puerto
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando para iniciar
CMD ["gunicorn", \
     "--workers=2", \
     "--threads=2", \
     "--worker-class=uvicorn.workers.UvicornWorker", \
     "--bind=0.0.0.0:8000", \
     "--timeout=120", \
     "--access-logfile=-", \
     "--error-logfile=-", \
     "app:app"]
