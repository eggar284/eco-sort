#include <Servo.h>

// ── SERVOS ────────────────────────────────────────────
Servo sPlastico; // Pin 9
Servo sCarton;   // Pin 10
Servo sMetal;    // Pin 11
Servo sPecial;   // Pin 6

// ── SENSOR ULTRASONICO ────────────────────────────────
#define TRIG 7
#define ECHO 8

// ── DEBOUNCE ──────────────────────────────────────────
#define DISTANCE_THRESHOLD 8     // cm
#define DEBOUNCE_MS        2000  // 2 segundos entre detecciones
unsigned long lastDetectionTime = 0;

void setup() {
  Serial.begin(9600);

  sPlastico.attach(9);
  sCarton.attach(10);
  sMetal.attach(11);
  sPecial.attach(6);

  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);

  // Posición inicial
  sPlastico.write(0);
  sCarton.write(0);
  sMetal.write(90);
  sPecial.write(90);

  // Handshake: avisar a la Raspberry que el Arduino está listo
  delay(500);
  Serial.println("SERIAL_READY");
}

void loop() {
  // ── DETECCIÓN DE OBJETO CON DEBOUNCE ─────────────────
  unsigned long now = millis();
  if (now - lastDetectionTime >= DEBOUNCE_MS) {
    long dist = leerDistancia();
    if (dist > 0 && dist <= DISTANCE_THRESHOLD) {
      Serial.println("OBJETO_DETECTADO");
      lastDetectionTime = now;
    }
  }

  // ── RECIBIR COMANDOS DESDE RASPBERRY PI ──────────────
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "PLASTICO") moverPlastico();
    if (cmd == "CARTON")   moverCarton();
    if (cmd == "METAL")    moverMetal();
    if (cmd == "ESPECIAL") moverSpecial();
  }
}

// ── FUNCIONES DE SERVO (SIN CAMBIOS) ─────────────────

void moverPlastico() {
  sPlastico.write(65);
  delay(500);
  sPecial.write(0);
  delay(4000);
  p_inicial();
}

void moverCarton() {
  sCarton.write(65);
  delay(500);
  sPecial.write(0);
  delay(4000);
  p_inicial();
}

void moverMetal() {
  sMetal.write(115);
  delay(500);
  sPecial.write(0);
  delay(4000);
  p_inicial();
}

void moverSpecial() {
  sMetal.write(65);
  delay(500);
  sPecial.write(0);
  delay(4000);
  p_inicial();
}

void p_inicial() {
  sPlastico.write(0);
  sCarton.write(0);
  sMetal.write(90);
  sPecial.write(90);
}

// ── SENSOR DE DISTANCIA ───────────────────────────────
long leerDistancia() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  long duration = pulseIn(ECHO, HIGH, 30000); // timeout 30ms
  if (duration == 0) return -1;
  return duration / 58; // devuelve cm
}
