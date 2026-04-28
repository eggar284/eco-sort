# Servidor Web

Servidor Node.js + Express + Socket.IO que sirve el frontend, gestiona
usuarios (registro/login con JWT), almacena clasificaciones en MySQL y
hace de puente entre las máquinas físicas y los dashboards.

## Requisitos

- Node.js 18+
- MySQL 8+

## Instalación

```bash
npm install
cp .env.example .env
# editar .env con tus credenciales reales
```

## Base de datos

El servidor crea las tablas automáticamente al arrancar. Solo necesitas
crear la base vacía:

```sql
CREATE DATABASE ecosort CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## Correr

```bash
npm start
```

## Endpoints principales

- `POST /api/auth/register` — crear cuenta
- `POST /api/auth/login` — iniciar sesión, devuelve JWT
- `GET /api/user/me` — datos del usuario autenticado
- `GET /api/user/stats` — XP, total reciclados, ranking
- `GET /api/leaderboard` — top 10 usuarios
- `POST /api/machine/link` — vincular cuenta con código de máquina
- `POST /api/machine/unlink` — terminar sesión en la máquina

## Eventos Socket.IO clave

| Evento                    | Dirección       |
|---------------------------|-----------------|
| `registrar_maquina`       | Pi → Server     |
| `usuario_vinculado`       | Server → Pi     |
| `camera_frame_push`       | Pi → Server     |
| `resultado_clasificacion` | Pi → Server     |
| `clasificacion_resultado` | Server → Web/Pi |
| `sesion_terminada`        | Server → Pi     |

## Simulador

Para probar sin hardware físico:

```bash
node raspberry-sim.js
# abre http://localhost:3001
```