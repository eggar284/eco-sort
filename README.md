# ECO-SORT

Intelligent waste separation system with AI, IoT, and gamification.
A physical machine connected to the cloud sorts the material placed in front of it 
and deposits it in the correct container, while adding points to your account.

**Web Site:** [ecosort.online](https://ecosort.online)

---

## How does it work?

```
┌─────────────────┐    HTTPS     ┌─────────────────┐
│  web screen     │◀────────────▶│  Server Node.js │
│ (cliente / dash)│   Socket.IO  │  + MySQL + JWT  │
└─────────────────┘              └────────┬────────┘
                                          │ Socket.IO
                                          ▼
┌─────────────────┐               ┌────────────────┐
│  Cloud Run / AI │◀──HTTPS POST──│  Raspberry Pi  │
│ Recycling-Net-11│  base64 img   │ Python+Pygame  │
└─────────────────┘               └───────┬────────┘
                                          │ Serial USB
                                          ▼
                                  ┌────────────────┐
                                  │  Arduino UNO   │
                                  │ Servos + HC-SR04│
                                  └────────────────┘
```

1. The user creates an account on the website and receives a JWT token.
2. The machine's screen displays a code (`ECO-001`) and a QR code.
3. The user enters the code on the website → their account is linked.
4. The ultrasonic sensor detects an object smaller than 8 cm and notifies the Pi.
5. The Pi captures a photo and sends it to the API on GCP.
6. The AI ​​(`prithivMLmods/Recycling-Net-11`) returns the category.
7. The Pi instructs the Arduino to move the servos to the correct container.
8. The server awards XP to the user and updates the dashboard in real time.

---

## Repo structure

```
eco-sort/
├── web/              Server Node.js + frontend
├── ai-model/         API FastAPI the model on Cloud Run (GCP)
└── raspberry-pi/     Python Controler + Arduino firmware 
```

Each folder has its own README file with specific instructions.

---

## Technical stack

| Capa            | Tecnología                                     |
|-----------------|------------------------------------------------|
| Frontend        | HTML5, CSS, JS vanilla, Socket.IO              |
| Backend web     | Node.js, Express, Socket.IO, MySQL, JWT, bcrypt|
| API AI          | FastAPI, Hugging Face Transformers, PyTorch    |
| Hosting AI      | Google Cloud Run + Docker                      |
| Hardware        | Raspberry Pi 4, Arduino UNO, HC-SR04, 4 servos |
| Screen          | TFT 3.5" SPI (fbtft → /dev/fb1)                |
| Pi software     | Python 3, pygame, OpenCV, python-socketio      |

---

## In case you want to do a quick deployment

**1. Web server** (`web/`)
```bash
cd web
npm install
cp .env.example .env  # Edit with your credentials
npm start
```

**2. API AI** (`ai-model/`)
```bash
cd ai-model
docker build -t ecosort-ai .
gcloud run deploy ecosort-ai --image=ecosort-ai --region=us-central1
```

**3. Raspberry Pi** (`raspberry-pi/`)
- Sube `arduino_firmware/arduino_firmware.ino` with the Arduino IDE.
- Connect the Arduino to the Pi via USB.
- On the Pi: `pip install -r requirements.txt && python3 ecosort_raspberry.py`

---

## License

MIT — ver [LICENSE](LICENSE).
