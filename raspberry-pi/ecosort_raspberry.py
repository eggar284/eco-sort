#!/usr/bin/env python3
"""
ECO-SORT — Programa Unificado Raspberry Pi
═══════════════════════════════════════════════════════════════
Combina en UN solo proceso:
  - Control del Arduino (servos + sensor ultrasónico HC-SR04)
  - Captura de cámara USB y streaming al dashboard web
  - Clasificación IA vía API GCP (Recycling-Net-11)
  - Pantalla táctil 3.5" HDMI con pygame
  - Comunicación con server.js vía Socket.IO

Una sola conexión socket  ➜  no hay re-registros que peleen.
Verificación de hardware  ➜  letras rojas chiquitas si falla.
Timer de inactividad      ➜  manejado por el servidor (3 min).

Uso:
    python3 ecosort_raspberry.py
"""

import os
import sys
import io
import time
import base64
import threading
import requests
import socketio
import qrcode
import pygame
import serial
import cv2
import numpy as np
from PIL import Image

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
SERVER_URL   = "https://ecosort.online"
WEB_URL      = "https://ecosort.online"
API_URL      = "https://recycling-net-11-1021127731934.us-central1.run.app/predict-base64"
MACHINE_CODE = "ECO-001"

# Pantalla
SCREEN_W = 480
SCREEN_H = 320

# Timing
MIN_SCAN_INTERVAL = 3.0   # segundos mínimos entre clasificaciones
CAM_FPS           = 5     # frames por segundo al dashboard

# Serial
SERIAL_BAUD  = 9600
SERIAL_PORTS = ["/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyUSB1", "/dev/ttyACM1"]

# Mapeo de comando del API → comando del Arduino
# El API devuelve: L=plástico, C=cartón, M=metal, V=vidrio, P=papel, R=residuo
# El Arduino entiende: PLASTICO, CARTON, METAL, ESPECIAL
API_TO_ARDUINO = {
    "L": "PLASTICO",
    "C": "CARTON",
    "M": "METAL",
    "V": "ESPECIAL",   # vidrio → contenedor especial
    "P": "CARTON",     # papel → mismo bin que cartón
    "R": "ESPECIAL",   # residuo → especial
}

# Colores
BG          = (15, 31, 22)
GREEN       = (0, 194, 124)
GREEN_DARK  = (0, 153, 96)
GREEN_LIGHT = (0, 232, 154)
WHITE       = (255, 255, 255)
GRAY        = (100, 160, 130)
DARK_CARD   = (25, 55, 38)
RED         = (239, 68, 68)
AMBER       = (245, 158, 11)

# ═══════════════════════════════════════════════════════════════
# ESTADO GLOBAL
# ═══════════════════════════════════════════════════════════════
state = {
    "screen":       "welcome",   # welcome | linked | recycling
    "lang":         "es",
    "user_name":    "",
    "user_id":      None,
    "last_result":  None,
    "connected":    False,
    "show_hi":      True,
    "scanning":     False,
    "last_scan_t":  0,
    "transmitting": True,
    "errors":       [],          # ['CAMARA', 'ARDUINO']
}

# ═══════════════════════════════════════════════════════════════
# HARDWARE — CÁMARA
# ═══════════════════════════════════════════════════════════════
cam = None
cam_lock = threading.Lock()

def init_camera():
    """Abre /dev/video0 y verifica que entregue al menos un frame."""
    global cam
    try:
        cam = cv2.VideoCapture(0)
        if not cam.isOpened():
            cam = None
            return False
        cam.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        ret, _ = cam.read()
        if not ret:
            cam.release()
            cam = None
            return False
        print("[CAM] Cámara USB lista ✅")
        return True
    except Exception as e:
        print(f"[CAM] Excepción init: {e}")
        cam = None
        return False

def capture_frame_b64(quality=85):
    """Captura un frame JPEG y lo devuelve como base64 (sin prefijo data:)."""
    if cam is None:
        return None
    try:
        with cam_lock:
            ret, frame = cam.read()
        if not ret or frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            return None
        return base64.b64encode(buf.tobytes()).decode()
    except Exception as e:
        print(f"[CAM] Error captura: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
# HARDWARE — ARDUINO SERIAL
# ═══════════════════════════════════════════════════════════════
arduino = None

def init_arduino(timeout_s=8):
    """
    Prueba puertos en orden, espera handshake 'SERIAL_READY' del Arduino.
    Devuelve True si conecta, False si ningún puerto responde a tiempo.
    """
    global arduino
    for port in SERIAL_PORTS:
        try:
            arduino = serial.Serial(port, SERIAL_BAUD, timeout=2)
            time.sleep(2)  # reset post-apertura del Arduino
            print(f"[SERIAL] Probando {port} — esperando SERIAL_READY...")
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if arduino.in_waiting:
                    line = arduino.readline().decode(errors="ignore").strip()
                    if line:
                        print(f"[SERIAL] Arduino → {line}")
                    if line == "SERIAL_READY":
                        print(f"[SERIAL] Handshake OK en {port} ✅")
                        return True
                time.sleep(0.1)
            print(f"[SERIAL] Timeout en {port}")
            arduino.close()
            arduino = None
        except Exception as e:
            print(f"[SERIAL] {port}: {e}")
            arduino = None
    return False

def send_to_arduino(command):
    """Envía un comando al Arduino terminado en \\n. Tolera arduino=None."""
    if arduino and arduino.is_open:
        try:
            arduino.write(f"{command}\n".encode())
            print(f"[SERIAL] → {command}")
        except Exception as e:
            print(f"[SERIAL] Error '{command}': {e}")
    else:
        print(f"[SERIAL] (sin arduino) Ignoro: {command}")

# ═══════════════════════════════════════════════════════════════
# CLASIFICACIÓN IA
# ═══════════════════════════════════════════════════════════════
def classify_image(b64_image):
    """Llama a la API en GCP y devuelve dict con resultado, o None."""
    try:
        r = requests.post(API_URL, json={"image_base64": b64_image}, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "predictions" in data:
            return data["predictions"][0]
        return data
    except requests.Timeout:
        print("[API] Timeout — IA no respondió")
        return None
    except Exception as e:
        print(f"[API] Error: {e}")
        return None

def process_object():
    """Flujo completo: captura → clasifica → mueve servo → reporta al server."""
    state["scanning"] = True
    print("[SCAN] Objeto detectado — iniciando clasificación")

    send_to_arduino("SCANNING")

    b64 = capture_frame_b64(quality=90)
    if not b64:
        print("[SCAN] Sin frame — abortando")
        state["scanning"] = False
        send_to_arduino("RESET")
        return

    print("[API] Enviando imagen a GCP...")
    result = classify_image(b64)
    if not result:
        print("[API] Sin resultado — abortando")
        state["scanning"] = False
        send_to_arduino("RESET")
        return

    cat       = result.get("categoria", "DESCONOCIDO")
    cmd_api   = result.get("comando_servo", "?")
    xp        = result.get("xp_puntos", result.get("xp_ganado", 10))
    confianza = result.get("confianza", 0)
    material  = result.get("label_original", cat)

    arduino_cmd = API_TO_ARDUINO.get(cmd_api, "ESPECIAL")
    print(f"[API] {cat} ({confianza*100:.1f}%) +{xp}XP → Arduino: {arduino_cmd}")

    send_to_arduino(arduino_cmd)

    if sio.connected:
        try:
            sio.emit("resultado_clasificacion", {
                "codigo":    MACHINE_CODE,
                "material":  material,
                "categoria": cat,
                "confianza": confianza,
                "xp_ganado": xp,
            })
        except Exception as e:
            print(f"[SOCKET] Error emit resultado: {e}")

    state["last_scan_t"] = time.time()
    time.sleep(MIN_SCAN_INTERVAL)
    state["scanning"] = False
    send_to_arduino("READY")
    print("[SCAN] Listo para siguiente objeto")

# ═══════════════════════════════════════════════════════════════
# THREAD — LECTOR DEL ARDUINO
# ═══════════════════════════════════════════════════════════════
def arduino_reader_loop():
    """Escucha el serial y dispara process_object() en OBJETO_DETECTADO."""
    while True:
        try:
            if arduino and arduino.is_open and arduino.in_waiting:
                line = arduino.readline().decode(errors="ignore").strip()
                if line == "OBJETO_DETECTADO":
                    if state["scanning"]:
                        pass  # ignorar, ya estamos clasificando
                    elif not state["user_id"]:
                        print("[SENSOR] OBJETO_DETECTADO ignorado: sin usuario vinculado")
                    elif (time.time() - state["last_scan_t"]) < MIN_SCAN_INTERVAL:
                        pass  # debounce de software
                    else:
                        print("[SENSOR] OBJETO_DETECTADO recibido")
                        threading.Thread(target=process_object, daemon=True).start()
                elif line:
                    print(f"[SERIAL] Arduino: {line}")
        except Exception as e:
            print(f"[SERIAL_LOOP] {e}")
        time.sleep(0.05)

# ═══════════════════════════════════════════════════════════════
# THREAD — STREAMING DE CÁMARA AL DASHBOARD
# ═══════════════════════════════════════════════════════════════
def camera_stream_loop():
    """Envía frames al servidor a CAM_FPS para el dashboard web."""
    interval = 1.0 / CAM_FPS
    while True:
        try:
            if sio.connected and state["transmitting"] and cam is not None:
                b64 = capture_frame_b64(quality=55)
                if b64:
                    sio.emit("camera_frame_push", {
                        "frame":  b64,
                        "codigo": MACHINE_CODE,
                    })
        except Exception as e:
            print(f"[STREAM] {e}")
        time.sleep(interval)

# ═══════════════════════════════════════════════════════════════
# SOCKET.IO  (UNA SOLA CONEXIÓN PARA TODO EL PROGRAMA)
# ═══════════════════════════════════════════════════════════════
sio = socketio.Client(reconnection=True, reconnection_delay=3, reconnection_attempts=0)

@sio.event
def connect():
    state["connected"] = True
    print("[SOCKET] Conectado al servidor ✅")
    sio.emit("registrar_maquina", {
        "codigo":         MACHINE_CODE,
        "estado_inicial": "disponible",
    })
    if state["errors"]:
        # Avisar al dashboard si arrancamos con hardware faltante
        try:
            sio.emit("error_sistema",
                     {"mensaje": "Falta: " + ", ".join(state["errors"])})
        except Exception:
            pass

@sio.event
def disconnect():
    state["connected"] = False
    print("[SOCKET] Desconectado del servidor")

@sio.on("usuario_vinculado")
def on_user_linked(data):
    state["user_name"] = data.get("nombre", "")
    state["lang"]      = data.get("idioma", "es")
    state["user_id"]   = data.get("id")
    state["screen"]    = "linked"
    print(f"[SOCKET] Usuario vinculado: {state['user_name']} "
          f"({state['lang']}) id={state['user_id']}")

@sio.on("sesion_terminada")
def on_session_ended(data):
    motivo = data.get("motivo", "")
    print(f"[SOCKET] Sesión terminada: {motivo}")
    state["user_id"]     = None
    state["user_name"]   = ""
    state["scanning"]    = False
    state["screen"]      = "welcome"
    state["last_result"] = None
    send_to_arduino("RESET")

@sio.on("clasificacion_resultado")
def on_result(data):
    state["last_result"] = data
    state["screen"]      = "recycling"
    print(f"[SOCKET] Resultado web: {data.get('categoria')} "
          f"+{data.get('xp_ganado')}XP")

@sio.on("desconectado")
def on_kicked(data):
    print(f"[SOCKET] Servidor nos pateó: {data}")

def socket_connect_loop():
    """Mantiene la conexión viva. Reintenta cada 5s si cae."""
    while True:
        try:
            if not sio.connected:
                sio.connect(SERVER_URL, transports=["websocket"])
                sio.wait()
        except Exception as e:
            print(f"[SOCKET] Error conexión: {e} — reintento en 5s")
            time.sleep(5)

# ═══════════════════════════════════════════════════════════════
# PYGAME — PANTALLA
# ═══════════════════════════════════════════════════════════════
# Soporte para pantallas SPI/GPIO (fbtft) que exponen /dev/fb1.
# SDL2 no maneja /dev/fb1 directamente, así que pygame renderiza
# en RAM (driver 'dummy') y nosotros empujamos el buffer al fb a mano.
# ═══════════════════════════════════════════════════════════════
pygame.font.init()  # las fuentes no necesitan driver de video


class SPIFramebuffer:
    """
    Empuja una pygame.Surface directamente a /dev/fbN.
    Soporta bpp = 16 (RGB565)  y  bpp = 32 (XRGB8888).
    """

    def __init__(self, dev_path):
        self.path = dev_path
        fb_num = dev_path.replace("/dev/fb", "")
        sysroot = f"/sys/class/graphics/fb{fb_num}"

        with open(f"{sysroot}/virtual_size") as f:
            w, h = f.read().strip().split(",")
            self.w, self.h = int(w), int(h)
        with open(f"{sysroot}/bits_per_pixel") as f:
            self.bpp = int(f.read().strip())
        try:
            with open(f"{sysroot}/stride") as f:
                self.stride = int(f.read().strip())
        except Exception:
            self.stride = self.w * (self.bpp // 8)

        self.fd = open(dev_path, "wb", buffering=0)
        print(f"[FB] {dev_path}  {self.w}x{self.h}  {self.bpp}bpp  "
              f"stride={self.stride}")

    def blit(self, surface):
        """Convierte la surface al formato del fb y la escribe."""
        if surface.get_size() != (self.w, self.h):
            surface = pygame.transform.scale(surface, (self.w, self.h))

        # pygame.surfarray.pixels3d → shape (W, H, 3)  RGB
        # se transpone a (H, W, 3) para coincidir con el orden del fb
        arr = pygame.surfarray.array3d(surface).swapaxes(0, 1)

        if self.bpp == 16:
            r = (arr[:, :, 0].astype(np.uint16) >> 3) << 11
            g = (arr[:, :, 1].astype(np.uint16) >> 2) << 5
            b = (arr[:, :, 2].astype(np.uint16) >> 3)
            data = (r | g | b).tobytes()
        elif self.bpp == 32:
            zeros = np.zeros((self.h, self.w, 1), dtype=np.uint8)
            # Formato típico fb: BGRX
            bgra = np.concatenate(
                [arr[:, :, 2:3], arr[:, :, 1:2], arr[:, :, 0:1], zeros],
                axis=2,
            )
            data = bgra.tobytes()
        else:
            return  # bpp no soportado

        try:
            self.fd.seek(0)
            self.fd.write(data)
        except Exception as e:
            print(f"[FB] Error write: {e}")

    def close(self):
        try:
            self.fd.close()
        except Exception:
            pass


# Instancia global del framebuffer SPI (None si no se usa)
spi_fb = None


def init_display():
    """
    Decide cómo dibujar:
      1. Si existe /dev/fb1 (pantalla SPI tipo 3.5"): driver 'dummy'
         + push manual a /dev/fb1 cada frame.
      2. Si hay DISPLAY (escritorio):  auto → x11 → wayland.
      3. Headless con HDMI moderno:    kmsdrm → fbdev → x11 → auto.
      4. Último recurso: 'dummy' (sin pantalla, pero el programa sigue).
    """
    global spi_fb

    # Caso 1: pantalla SPI/GPIO
    if os.path.exists("/dev/fb1"):
        try:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            try:
                pygame.display.quit()
            except Exception:
                pass
            pygame.display.init()
            surf = pygame.display.set_mode((SCREEN_W, SCREEN_H))
            spi_fb = SPIFramebuffer("/dev/fb1")
            print(f"[PYGAME] Modo SPI: dummy + /dev/fb1  ✅")
            return surf
        except Exception as e:
            print(f"[PYGAME] /dev/fb1 falló ({e}) — probando otros drivers")
            spi_fb = None

    # Caso 2/3/4: drivers SDL normales
    if "DISPLAY" in os.environ:
        candidates = [None, "x11", "wayland"]
    else:
        candidates = ["kmsdrm", "fbdev", "x11", None]
    candidates.append("dummy")

    last_err = None
    for drv in candidates:
        try:
            if drv is None:
                os.environ.pop("SDL_VIDEODRIVER", None)
            else:
                os.environ["SDL_VIDEODRIVER"] = drv
                if drv == "fbdev":
                    os.environ["SDL_FBDEV"] = "/dev/fb0"

            try:
                pygame.display.quit()
            except Exception:
                pass
            pygame.display.init()

            try:
                surf = pygame.display.set_mode(
                    (SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
            except Exception:
                surf = pygame.display.set_mode((SCREEN_W, SCREEN_H))

            print(f"[PYGAME] Video driver: {drv or 'auto'}  ✅")
            return surf
        except Exception as e:
            last_err = e
            print(f"[PYGAME] Driver '{drv or 'auto'}' falló: {e}")
            continue

    raise RuntimeError(f"Ningún driver SDL funcionó. Último error: {last_err}")


screen = init_display()
pygame.display.set_caption("ECO-SORT")
clock = pygame.time.Clock()

def load_font(size, bold=False):
    try:
        return pygame.font.SysFont("dejavusans", size, bold=bold)
    except Exception:
        return pygame.font.Font(None, size)

font_huge  = load_font(72, bold=True)
font_big   = load_font(48, bold=True)
font_med   = load_font(28)
font_small = load_font(20)
font_xs    = load_font(16)
font_tiny  = load_font(13)

# QR code
def generate_qr_surface(url, size=130):
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    pil_img = Image.open(buf).resize((size, size), Image.NEAREST)
    # qrcode genera la imagen en modo '1' (1-bit) o 'L'; pygame solo
    # entiende RGB/RGBA, así que convertimos siempre a RGB.
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    return pygame.image.fromstring(pil_img.tobytes(), pil_img.size, pil_img.mode)

qr_surface = generate_qr_surface(WEB_URL, size=130)

# ── Helpers de dibujo ─────────────────────────────────
def draw_rounded_rect(surf, color, rect, radius=12, alpha=255):
    s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), (0, 0, rect[2], rect[3]),
                     border_radius=radius)
    surf.blit(s, (rect[0], rect[1]))

def draw_text_centered(surf, text, font, color, y, shadow=False):
    if shadow:
        sh = font.render(text, True, (0, 0, 0))
        surf.blit(sh, sh.get_rect(center=(SCREEN_W // 2 + 2, y + 2)))
    rendered = font.render(text, True, color)
    rect = rendered.get_rect(center=(SCREEN_W // 2, y))
    surf.blit(rendered, rect)
    return rect

def draw_button(surf, text, font, rect, bg_color, text_color=WHITE, radius=10):
    draw_rounded_rect(surf, bg_color, rect, radius)
    rendered = font.render(text, True, text_color)
    tr = rendered.get_rect(center=(rect[0] + rect[2] // 2,
                                   rect[1] + rect[3] // 2))
    surf.blit(rendered, tr)
    return pygame.Rect(rect)

def draw_hardware_errors():
    """Letras rojas chiquitas en la parte inferior si falta hardware."""
    if not state["errors"]:
        return
    msg = "Falta: " + ", ".join(state["errors"])
    t = font_tiny.render(msg, True, RED)
    screen.blit(t, (8, SCREEN_H - 16))

# ── Pantalla: WELCOME ─────────────────────────────────
anim_t       = 0
anim_opacity = 255
anim_dir     = -1

def draw_welcome():
    global anim_t, anim_opacity, anim_dir
    screen.fill(BG)

    # Decoración fondo
    for i in range(5):
        r = 60 + i * 35
        alpha = 20 - i * 3
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        pygame.draw.circle(s, (*GREEN, max(0, alpha)),
                           (SCREEN_W - 60, 60), r)
        screen.blit(s, (0, 0))

    # Saludo con fade alterno
    anim_t += 1
    if anim_t % 3 == 0:
        anim_opacity += anim_dir * 6
        if anim_opacity <= 30:
            anim_dir = 1
            state["show_hi"] = not state["show_hi"]
        if anim_opacity >= 255:
            anim_opacity = 255
            anim_dir = -1

    greeting = "HI!" if state["show_hi"] else "¡HOLA!"
    color_a = tuple(min(255, int(c * (anim_opacity / 255))) for c in GREEN_LIGHT)
    gr = font_huge.render(greeting, True, color_a)
    screen.blit(gr, gr.get_rect(center=(160, 80)))

    sub = "Welcome to ECO-SORT" if state["show_hi"] else "Bienvenido a ECO-SORT"
    draw_text_centered(screen, sub, font_small, GRAY, 130)

    # Caja del código
    draw_rounded_rect(screen, DARK_CARD, (20, 155, 220, 50), radius=10)
    screen.blit(font_xs.render("TU CÓDIGO:", True, GRAY), (35, 162))
    screen.blit(font_med.render(MACHINE_CODE, True, GREEN_LIGHT), (35, 178))

    # Pasos
    steps_es = ["1. Escanea el QR",
                "2. Crea cuenta / Inicia sesión",
                f"3. Ingresa código: {MACHINE_CODE}"]
    steps_en = ["1. Scan the QR code",
                "2. Create account / Log in",
                f"3. Enter code: {MACHINE_CODE}"]
    steps = steps_en if state["show_hi"] else steps_es
    for i, step in enumerate(steps):
        screen.blit(font_xs.render(step, True, WHITE), (25, 215 + i * 20))

    # QR
    screen.blit(qr_surface, (SCREEN_W - 145, 145))
    screen.blit(font_xs.render("ecosort.online", True, GRAY),
                (SCREEN_W - 145, 282))

    # Indicador de conexión
    pygame.draw.circle(screen, GREEN if state["connected"] else RED,
                       (SCREEN_W - 12, 12), 6)

    draw_hardware_errors()

# ── Pantalla: LINKED ──────────────────────────────────
linked_anim = 0

def draw_linked():
    global linked_anim
    screen.fill(BG)
    linked_anim += 1

    pulse = abs((linked_anim % 60) - 30) / 30
    r = int(40 + pulse * 20)
    s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    pygame.draw.circle(s, (*GREEN, 15), (SCREEN_W // 2, 90), r + 60)
    screen.blit(s, (0, 0))

    lang = state["lang"]
    name = state["user_name"]
    greeting = f"Hi, {name}!" if lang == "en" else f"¡Hola, {name}!"

    draw_text_centered(screen, "♻", font_big, GREEN, 60)
    draw_text_centered(screen, greeting, font_med, WHITE, 115, shadow=True)

    instr = ("Place your waste in front of the camera"
             if lang == "en" else
             "Coloca el residuo frente a la cámara")
    words = instr.split()
    mid = len(words) // 2
    draw_text_centered(screen, " ".join(words[:mid]), font_small, GRAY, 150)
    draw_text_centered(screen, " ".join(words[mid:]), font_small, GRAY, 172)

    draw_rounded_rect(screen, DARK_CARD, (20, 195, SCREEN_W - 40, 40),
                      radius=8)
    status_txt = ("🟢 Ready — Sensor active" if lang == "en"
                  else "🟢 Listo — Sensor activo")
    screen.blit(font_small.render(status_txt, True, GREEN), (35, 207))

    btn = draw_button(screen,
                      "Cerrar sesión" if lang == "es" else "End session",
                      font_small, (20, 248, 200, 38),
                      (80, 20, 20), RED, radius=8)

    pygame.draw.circle(screen, GREEN if state["connected"] else RED,
                       (SCREEN_W - 12, 12), 6)
    draw_hardware_errors()
    return btn

# ── Pantalla: RECYCLING ───────────────────────────────
result_timer = 0

def draw_recycling():
    global result_timer
    screen.fill(BG)
    result_timer += 1

    data = state["last_result"] or {}
    cat       = data.get("categoria", "—")
    mat       = data.get("material", data.get("material_detectado", ""))
    conf      = data.get("confianza", 0)
    xp        = data.get("xp_ganado", 0)
    lang      = state["lang"]

    cat_colors = {
        "PLASTICO": (59, 130, 246),
        "CARTON":   (180, 100, 30),
        "METAL":    (148, 163, 184),
        "VIDRIO":   (16, 185, 129),
        "UNICEL":   (245, 158, 11),
        "ESPECIAL": (239, 68, 68),
        "PAPEL":    (139, 92, 246),
        "RESIDUO":  (100, 100, 100),
    }
    color = cat_colors.get(cat, GREEN)

    draw_rounded_rect(screen, color, (0, 0, SCREEN_W, 100), radius=0, alpha=40)
    draw_text_centered(screen, cat, font_big, color, 50, shadow=True)

    if mat:
        draw_text_centered(screen, mat, font_small, WHITE, 98)

    conf_txt = (f"{conf*100:.1f}% confidence" if lang == "en"
                else f"{conf*100:.1f}% confianza")
    draw_text_centered(screen, conf_txt, font_small, GRAY, 125)

    draw_text_centered(screen, f"+{xp} XP ⚡", font_big, AMBER, 168, shadow=True)

    progress = min(result_timer / 150, 1.0)
    bar_w    = int((SCREEN_W - 40) * progress)
    draw_rounded_rect(screen, DARK_CARD, (20, 215, SCREEN_W - 40, 8), radius=4)
    if bar_w > 0:
        draw_rounded_rect(screen, GREEN, (20, 215, bar_w, 8), radius=4)

    hint = "Next object..." if lang == "en" else "Siguiente objeto..."
    draw_text_centered(screen, hint, font_xs, GRAY, 235)

    edu = data.get("info_educativa", "")
    if edu:
        words = edu.split()
        chunks, line = [], []
        for w in words:
            line.append(w)
            if len(" ".join(line)) > 52:
                chunks.append(" ".join(line[:-1]))
                line = [w]
        if line:
            chunks.append(" ".join(line))
        for i, chunk in enumerate(chunks[:2]):
            screen.blit(font_xs.render(chunk, True, GRAY),
                        (20, 250 + i * 17))

    draw_hardware_errors()

    if result_timer > 150:  # 5 segundos a 30fps
        result_timer = 0
        state["screen"] = "linked"

# ═══════════════════════════════════════════════════════════════
# ACCIONES
# ═══════════════════════════════════════════════════════════════
def end_session():
    """Botón 'Cerrar sesión' o tecla Q."""
    if sio.connected:
        try:
            sio.emit("parar_sesion", {"codigo": MACHINE_CODE})
        except Exception:
            pass
    state["screen"]      = "welcome"
    state["user_name"]   = ""
    state["user_id"]     = None
    state["last_result"] = None
    send_to_arduino("RESET")

# ═══════════════════════════════════════════════════════════════
# VERIFICACIÓN DE HARDWARE
# ═══════════════════════════════════════════════════════════════
print("\n[INIT] ════ Verificando hardware ════")

if not init_camera():
    state["errors"].append("CÁMARA")
    print("[INIT] ⚠️  CÁMARA no disponible")
else:
    print("[INIT] ✅ CÁMARA OK")

if not init_arduino(timeout_s=8):
    state["errors"].append("ARDUINO")
    print("[INIT] ⚠️  ARDUINO no disponible")
else:
    print("[INIT] ✅ ARDUINO OK")

if state["errors"]:
    print(f"[INIT] ⚠️  Funcionando en modo limitado — Falta: "
          f"{', '.join(state['errors'])}")
else:
    print("[INIT] ✅ Sistema completo")

# ═══════════════════════════════════════════════════════════════
# LANZAR THREADS DE FONDO
# ═══════════════════════════════════════════════════════════════
threading.Thread(target=socket_connect_loop, daemon=True).start()
threading.Thread(target=camera_stream_loop,  daemon=True).start()
threading.Thread(target=arduino_reader_loop, daemon=True).start()

print(f"\n🌱 ECO-SORT Raspberry Pi (unificado)")
print(f"   Servidor : {SERVER_URL}")
print(f"   Código   : {MACHINE_CODE}")
print(f"   Cámara   : {'✅' if cam is not None else '❌'} | "
      f"Arduino : {'✅' if arduino is not None else '❌'}\n")

# ═══════════════════════════════════════════════════════════════
# LOOP PRINCIPAL DE PYGAME (debe correr en el hilo principal)
# ═══════════════════════════════════════════════════════════════
btn_end_session = None
running = True

try:
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_q:
                    end_session()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                if state["screen"] == "linked" and btn_end_session:
                    if btn_end_session.collidepoint(pos):
                        end_session()

        if state["screen"] == "welcome":
            draw_welcome()
        elif state["screen"] == "linked":
            btn_end_session = draw_linked()
        elif state["screen"] == "recycling":
            draw_recycling()

        pygame.display.flip()
        if spi_fb is not None:
            spi_fb.blit(screen)
        clock.tick(30)

except KeyboardInterrupt:
    print("\n[EXIT] Ctrl+C recibido")
finally:
    print("[EXIT] Cerrando ECO-SORT...")
    if sio.connected:
        try:
            sio.emit("cambiar_estado",
                     {"codigo": MACHINE_CODE, "estado": "apagado"})
            sio.disconnect()
        except Exception:
            pass
    if cam is not None:
        cam.release()
    if arduino and arduino.is_open:
        arduino.close()
    if spi_fb is not None:
        spi_fb.close()
    pygame.quit()
    print("[EXIT] Limpieza completa ✅")
    sys.exit(0)
