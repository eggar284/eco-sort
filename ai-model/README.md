# API de Clasificación (Recycling-Net-11)

API en FastAPI que envuelve el modelo `prithivMLmods/Recycling-Net-11`
de Hugging Face para clasificar imágenes de residuos en 11 categorías.

Pensada para correr en Google Cloud Run con Docker.

## Endpoints

- `GET /health` — verificación de estado, indica si el modelo está cargado.
- `GET /` — info general.
- `GET /categories` — categorías y mapeo a comandos de servo + XP.
- `POST /predict-upload` — `multipart/form-data` con campo `file`.
- `POST /predict-base64` — JSON `{ "image_base64": "..." }`.

Respuesta típica:

```json
{
  "categoria": "PLASTICO",
  "comando_servo": "L",
  "confianza": 0.9521,
  "label_original": "plastic",
  "xp_puntos": 6,
  "info_educativa": "El plástico tarda 500 años en descomponerse.",
  "timestamp": 1762000000.123
}
```

## Despliegue en Google Cloud Run

```bash
docker build -t gcr.io/TU-PROYECTO/ecosort-ai .
docker push gcr.io/TU-PROYECTO/ecosort-ai

gcloud run deploy ecosort-ai \
  --image=gcr.io/TU-PROYECTO/ecosort-ai \
  --region=us-central1 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --allow-unauthenticated \
  --min-instances=0
```

> **Tip:** sube `--min-instances=1` (~$5-10 USD/mes) para evitar cold
> starts. Con 0, tras 15 min de inactividad el container duerme y la
> primera petición tarda 30-60 s mientras carga el modelo.

## Probar local

```bash
pip install -r requirements.txt
python app.py
# http://localhost:8000/docs (Swagger automático)
```