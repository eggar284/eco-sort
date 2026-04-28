# Raspberry Pi — Controlador físico

Programa Python unificado que corre en la Raspberry Pi 4 conectada a
la máquina. Hace todo en un solo proceso (una sola conexión socket):

- Comunicación serial con el Arduino (sensor + servos)
- Captura y stream de la cámara USB al dashboard web
- Llamadas a la API de IA en GCP
- UI en pantalla TFT 3.5" SPI (`/dev/fb1`) con pygame
- Conexión Socket.IO al servidor `ecosort.online`

## Hardware

- Raspberry Pi 4 (4GB+, OS 64-bit)
- Pantalla TFT 3.5" SPI (chip ILI9486 / driver fbtft)
- Cámara USB UVC
- Arduino UNO conectado por USB
- Sensor ultrasónico HC-SR04 (TRIG=7, ECHO=8)
- 4 servos (pines 6, 9, 10, 11)

## Software (Pi)

```bash
sudo apt update
sudo apt install python3-pip python3-pygame python3-opencv \
                 python3-numpy python3-pil python3-serial python3-requests
pip3 install python-socketio[client] qrcode --break-system-packages
```

## Pantalla SPI

Habilita `dtoverlay=tft35a` (o el que corresponda) en
`/boot/firmware/config.txt` y verifica que aparezca `/dev/fb1`:

```bash
ls /dev/fb*
cat /sys/class/graphics/fb1/virtual_size
```

Asegúrate de que tu usuario está en los grupos correctos:

```bash
sudo usermod -aG video,render,input,tty $USER
```

## Arduino

1. Abre `arduino_firmware/arduino_firmware.ino` en el Arduino IDE.
2. Selecciona la placa Arduino UNO.
3. Sube el sketch.
4. Conéctalo al Pi por USB (`/dev/ttyUSB0` o `/dev/ttyACM0`).

## Correr el programa

```bash
python3 ecosort_raspberry.py
```

El programa:

1. Verifica cámara y Arduino al inicio.
2. Hace warm-up de la API GCP.
3. Mantiene keep-alive cada 4 minutos.
4. Espera vinculación de usuario desde la web.
5. Cuando el sensor detecta un objeto, captura → clasifica → mueve servos.

## Acceso directo en el escritorio

```bash
cat > ~/Desktop/EcoSort.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ECO-SORT
Exec=lxterminal -e "python3 /home/ecosort/ecosort_raspberry.py; bash"
Icon=/home/ecosort/logo_eco.png
Path=/home/ecosort
Terminal=false
StartupNotify=true
EOF
chmod +x ~/Desktop/EcoSort.desktop
```

Click derecho → Allow Launching la primera vez.