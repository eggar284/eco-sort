"""
Configuración centralizada para la aplicación
"""

import os
from typing import Dict, Any

# Configuración del modelo
MODEL_NAME = "prithivMLmods/Recycling-Net-11"
MODEL_TASK = "image-classification"

# Mapeo de categorías
CATEGORIES = {
    'cardboard': {
        'es_name': 'Cartón',
        'servo_cmd': 'C',
        'xp': 8,
        'info': 'Reciclar cartón ahorra 17 árboles por tonelada.'
    },
    'glass': {
        'es_name': 'Vidrio',
        'servo_cmd': 'V',
        'xp': 5,
        'info': 'El vidrio es 100% reciclable sin perder calidad.'
    },
    # ... resto de categorías
}

# Configuración del servidor
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("PORT", 8000))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configuración de seguridad
API_KEY = os.getenv("API_KEY", None)  # Opcional: para autorización

# Configuración de inference
MAX_IMAGE_SIZE = 1024  # Píxeles
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
TIMEOUT_INFERENCE = 120  # Segundos