#!/usr/bin/env python3
"""
FastAPI Server para Recycling-Net-11 Model
Recibe imágenes y devuelve predicciones de clasificación
"""

import os
import base64
import logging
from datetime import datetime
from io import BytesIO
from typing import Optional
import json

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from PIL import Image
import numpy as np
import torch
from transformers import pipeline

# ============================================================================
# CONFIGURACIÓN Y CONSTANTES
# ============================================================================

# Crear logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mapeo de categorías: label original → categoría personalizada
CATEGORY_MAPPING = {
    'cardboard': {
        'categoria': 'CARTON',
        'comando_servo': 'C',
        'xp_puntos': 8,
        'info_educativa': 'Reciclar cartón ahorra 17 árboles por tonelada.'
    },
    'glass': {
        'categoria': 'VIDRIO',
        'comando_servo': 'V',
        'xp_puntos': 5,
        'info_educativa': 'El vidrio es 100% reciclable sin perder calidad.'
    },
    'metal': {
        'categoria': 'METAL',
        'comando_servo': 'M',
        'xp_puntos': 10,
        'info_educativa': 'Reciclar aluminio ahorra 95% de energía.'
    },
    'paper': {
        'categoria': 'PAPEL',
        'comando_servo': 'P',
        'xp_puntos': 4,
        'info_educativa': 'Se necesitan 24 árboles para hacer 1 tonelada de papel.'
    },
    'plastic': {
        'categoria': 'PLASTICO',
        'comando_servo': 'L',
        'xp_puntos': 6,
        'info_educativa': 'El plástico tarda 500 años en descomponerse.'
    },
    'trash': {
        'categoria': 'RESIDUO',
        'comando_servo': 'R',
        'xp_puntos': 0,
        'info_educativa': 'Los residuos no reciclables deben ir al basurero.'
    }
}

# ============================================================================
# CREAR APP FASTAPI
# ============================================================================

app = FastAPI(
    title="Recycling Net 11 API",
    description="Clasificación de objetos reciclables usando Hugging Face",
    version="1.0.0"
)

# Variable global para cargar el modelo UNA SOLA VEZ
MODEL = None

# ============================================================================
# FUNCIONES DE INICIALIZACIÓN
# ============================================================================

def load_model():
    """Cargar el modelo de Hugging Face UNA VEZ (startup)"""
    global MODEL
    logger.info("🤖 Cargando modelo Recycling-Net-11 desde Hugging Face...")
    
    try:
        # Esta línea descarga el modelo la primera vez
        # Luego lo cachea en ~/.cache/huggingface/
        MODEL = pipeline(
            "image-classification",
            model="prithivMLmods/Recycling-Net-11",
            device=0 if torch.cuda.is_available() else -1  # GPU si disponible
        )
        logger.info("✅ Modelo cargado exitosamente")
        logger.info(f"📍 Usando dispositivo: {'GPU' if torch.cuda.is_available() else 'CPU'}")
    except Exception as e:
        logger.error(f"❌ Error al cargar modelo: {e}")
        raise

# ============================================================================
# RUTAS/ENDPOINTS DE LA API
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Se ejecuta cuando la app inicia"""
    logger.info("🚀 Iniciando aplicación FastAPI...")
    load_model()
    logger.info("✅ Aplicación lista para recibir requests")

@app.get("/health")
async def health_check():
    """
    Health check simple
    Endpoint para verificar que la API está viva
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().timestamp(),
        "model_loaded": MODEL is not None
    }

@app.get("/")
async def root():
    """Ruta raíz - información general"""
    return {
        "nombre": "Recycling Net 11 API",
        "version": "1.0.0",
        "endpoints": [
            "GET /health - Verificar estado",
            "POST /predict-upload - Subir imagen",
            "POST /predict-base64 - Enviar como base64",
            "GET /categories - Ver todas las categorías"
        ],
        "modelo": "prithivMLmods/Recycling-Net-11"
    }

@app.get("/categories")
async def get_categories():
    """Devolver todas las categorías disponibles"""
    return {
        "total": len(CATEGORY_MAPPING),
        "categorias": list(CATEGORY_MAPPING.keys()),
        "mapeo_completo": CATEGORY_MAPPING
    }

@app.post("/predict-upload")
async def predict_upload(file: UploadFile = File(...)):
    """
    Endpoint 1: Subir imagen como archivo
    
    Uso:
    - Postman: POST /predict-upload, Tab "Body", "form-data", key "file" = imagen
    - Python: requests.post(url, files={"file": open("img.jpg", "rb")})
    """
    try:
        logger.info(f"📥 Recibido archivo: {file.filename}")
        
        # Leer contenido del archivo
        contents = await file.read()
        
        # Convertir a imagen PIL
        image = Image.open(BytesIO(contents))
        logger.info(f"✅ Imagen cargada: {image.size}")
        
        # PREDICCIÓN
        result = make_prediction(image)
        
        return JSONResponse(content=result, status_code=200)
    
    except Exception as e:
        logger.error(f"❌ Error en predicción: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/predict-base64")
async def predict_base64(payload: dict):
    """
    Endpoint 2: Enviar imagen como base64
    
    Payload JSON esperado:
    {
        "image_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    }
    
    Uso Python:
    import base64
    with open("image.jpg", "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    
    requests.post(url + "/predict-base64", 
                 json={"image_base64": b64})
    """
    try:
        # Extraer base64 del JSON
        image_base64 = payload.get("image_base64", "")
        
        if not image_base64:
            raise ValueError("image_base64 no proporcionado")
        
        # Si viene con prefijo "data:image/...", quitarlo
        if image_base64.startswith("data:"):
            image_base64 = image_base64.split(",")[1]
        
        # Decodificar
        image_bytes = base64.b64decode(image_base64)
        image = Image.open(BytesIO(image_bytes))
        
        logger.info(f"✅ Imagen base64 decodificada: {image.size}")
        
        # PREDICCIÓN
        result = make_prediction(image)
        
        return JSONResponse(content=result, status_code=200)
    
    except Exception as e:
        logger.error(f"❌ Error decodificando base64: {e}")
        raise HTTPException(status_code=400, detail=f"Error base64: {str(e)}")

# ============================================================================
# FUNCIÓN CENTRAL DE PREDICCIÓN
# ============================================================================

def make_prediction(image: Image.Image) -> dict:
    """
    LÓGICA CENTRAL: Procesar imagen y devolver JSON personalizado
    
    Args:
        image: PIL Image object
    
    Returns:
        dict: JSON con formato exacto requerido
    """
    
    # Asegurar que está en RGB (no RGBA)
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    logger.info(f"🔍 Prediciendo clase con modelo...")
    
    # PREDICCIÓN: El modelo devuelve lista de resultados
    predictions = MODEL(image)
    
    # predictions[0] es el resultado más probable
    # Formato: {'score': 0.9621, 'label': 'cardboard'}
    top_pred = predictions[0]
    
    label_original = top_pred['label'].lower()
    confianza = float(top_pred['score'])
    
    logger.info(f"📊 Resultado: {label_original} ({confianza:.4f})")
    
    # Buscar en nuestro mapeo
    if label_original not in CATEGORY_MAPPING:
        # Si el label no está en nuestro mapeo, usar un genérico
        logger.warning(f"⚠️ Label '{label_original}' no en mapeo, usando genérico")
        categoria_data = {
            'categoria': 'DESCONOCIDO',
            'comando_servo': '?',
            'xp_puntos': 0,
            'info_educativa': 'Categoría no reconocida.'
        }
    else:
        categoria_data = CATEGORY_MAPPING[label_original]
    
    # CONSTRUIR JSON PERSONALIZADO EXACTO
    response = {
        'categoria': categoria_data['categoria'],
        'comando_servo': categoria_data['comando_servo'],
        'confianza': confianza,
        'label_original': label_original,
        'xp_puntos': categoria_data['xp_puntos'],
        'info_educativa': categoria_data['info_educativa'],
        'timestamp': datetime.now().timestamp()
    }
    
    logger.info(f"✅ JSON generado: {response['categoria']}")
    
    return response

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Para desarrollo local:
    # python app.py
    # Luego visita: http://localhost:8000/docs
    
    uvicorn.run(
        app,
        host="0.0.0.0",  # Escuchar en TODAS las IPs (necesario para Docker)
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
