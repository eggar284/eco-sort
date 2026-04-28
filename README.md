# ECO-SORT

Sistema de separación inteligente de residuos con IA, IoT y gamificación.
Una máquina física conectada a la nube clasifica el material que le pones
enfrente y lo deposita en el contenedor correcto, mientras suma puntos a tu
cuenta.

**Sitio web:** [ecosort.online](https://ecosort.online)

---

## ¿Cómo funciona?

```
┌─────────────────┐    HTTPS     ┌─────────────────┐
│  Pantalla web   │◀────────────▶│  Server Node.js │
│ (cliente / dash)│   Socket.IO  │  + MySQL + JWT  │
└─────────────────┘              └────────┬────────┘
                                          │ Socket.IO
                                          ▼
┌─────────────────┐               ┌────────────────┐
│  Cloud Run / IA │◀──HTTPS POST──│  Raspberry Pi  │
│ Recycling-Net-11│  base64 img   │ Python+Pygame  │
└─────────────────┘               └───────┬────────┘
                                          │ Serial USB
                                          ▼
                                  ┌────────────────┐
                                  │  Arduino UNO   │
                                  │ Servos + HC-SR04│
                                  └────────────────┘
```

1. El usuario crea cuenta en la web y obtiene un token JWT.
2. La pantalla de la máquina muestra un código (`ECO-001`) y un QR.
3. El usuario escribe el código en la web → su cuenta queda vinculada.
4. El sensor ultrasónico detecta un objeto < 8 cm y avisa al Pi.
5. El Pi captura una foto y la manda a la API en GCP.
6. La IA (`prithivMLmods/Recycling-Net-11`) regresa la categoría.
7. El Pi ordena al Arduino mover los servos al contenedor correcto.
8. El servidor suma XP al usuario y actualiza el dashboard en tiempo real.

---

## Estructura del repo

```
eco-sort/
├── web/              Servidor Node.js + frontend
├── ai-model/         API FastAPI con el modelo en Cloud Run (GCP)
└── raspberry-pi/     Controlador Python + firmware Arduino
```

Cada carpeta tiene su propio README con instrucciones específicas.

---

## Stack técnico

| Capa            | Tecnología                                     |
|-----------------|------------------------------------------------|
| Frontend        | HTML5, CSS, JS vanilla, Socket.IO              |
| Backend web     | Node.js, Express, Socket.IO, MySQL, JWT, bcrypt|
| API IA          | FastAPI, Hugging Face Transformers, PyTorch    |
| Hosting IA      | Google Cloud Run + Docker                      |
| Hardware        | Raspberry Pi 4, Arduino UNO, HC-SR04, 4 servos |
| Pantalla        | TFT 3.5" SPI (fbtft → /dev/fb1)                |
| Pi software     | Python 3, pygame, OpenCV, python-socketio      |

---

## Despliegue rápido

**1. Servidor web** (`web/`)
```bash
cd web
npm install
cp .env.example .env  # editar con tus credenciales
npm start
```

**2. API IA** (`ai-model/`)
```bash
cd ai-model
docker build -t ecosort-ai .
gcloud run deploy ecosort-ai --image=ecosort-ai --region=us-central1
```

**3. Raspberry Pi** (`raspberry-pi/`)
- Sube `arduino_firmware/arduino_firmware.ino` con el Arduino IDE.
- Conecta el Arduino al Pi por USB.
- En el Pi: `pip install -r requirements.txt && python3 ecosort_raspberry.py`

---

## Licencia

MIT — ver [LICENSE](LICENSE).