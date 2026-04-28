"""
Funciones auxiliares
"""

import base64
import logging
from io import BytesIO
from typing import Tuple
import torch
from PIL import Image

logger = logging.getLogger(__name__)

def get_device() -> str:
    """Detectar si hay GPU disponible"""
    if torch.cuda.is_available():
        logger.info(f"🎮 GPU detectada: {torch.cuda.get_device_name(0)}")
        return "cuda"
    logger.info("💻 Usando CPU")
    return "cpu"

def resize_image(image: Image.Image, max_size: int = 1024) -> Image.Image:
    """Redimensionar imagen manteniendo aspecto"""
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return image

def encode_image_to_base64(image_path: str) -> str:
    """Convertir imagen a base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def decode_base64_to_image(base64_str: str) -> Image.Image:
    """Convertir base64 a imagen PIL"""
    if base64_str.startswith("data:"):
        base64_str = base64_str.split(",")[1]
    
    image_bytes = base64.b64decode(base64_str)
    return Image.open(BytesIO(image_bytes))

def get_memory_usage() -> dict:
    """Obtener uso de memoria actual"""
    if torch.cuda.is_available():
        return {
            "gpu_allocated_mb": torch.cuda.memory_allocated() / 1e6,
            "gpu_reserved_mb": torch.cuda.memory_reserved() / 1e6,
        }
    return {}


