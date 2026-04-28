// ══════════════════════════════════════════════════════
//  ECO-SORT — Simulador Raspberry Pi v2
//  - Se conecta automáticamente al servidor al iniciar
//  - Nombre de dispositivo configurable (sin ECO-001 default)
//  - Botones de material para simular clasificaciones
//  - Transmisión de cámara integrada
//  - Botón cortar transmisión / parar sesión
//  - Puerto independiente (3001), no necesita el mismo proceso
//
//  Uso: node raspberry-sim.js
//  Config: SIM_PORT=3001 SERVER_URL=http://localhost:3000
// ══════════════════════════════════════════════════════

const express  = require('express');
const http     = require('http');
const socketio = require('socket.io');
const { io: ioc } = require('socket.io-client');

const SIM_PORT   = process.env.SIM_PORT   || 3001;
const SERVER_URL = process.env.SERVER_URL || 'http://localhost:3000';

const app    = express();
const server = http.createServer(app);
const io     = socketio(server, { cors: { origin: '*' } });

// ── Estado del simulador ──────────────────────────────
let serverSocket  = null;
let machineCode   = null; // null = no configurado aún
let isConnected   = false;
let usuarioActual = null;

function broadcast(event, data) { io.emit(event, data); }

function connectToServer(code) {
  if (!code || code.trim() === '') return;
  if (serverSocket) serverSocket.disconnect();

  machineCode = code.trim().toUpperCase();
  console.log(`[SIM] Conectando al servidor como ${machineCode}...`);

  serverSocket = ioc(SERVER_URL, { transports: ['websocket'], reconnection: true, reconnectionDelay: 2000 });

  serverSocket.on('connect', () => {
    isConnected = true;
    // Registrar con estado 'disponible' desde el inicio
    serverSocket.emit('registrar_maquina', { codigo: machineCode, estado_inicial: 'disponible' });
    broadcast('status', { connected: true, code: machineCode, estado: 'disponible', msg: `✓ Conectado como ${machineCode} — disponible` });
    broadcast('machine_ready', { code: machineCode });
    console.log(`[SIM] Conectado como ${machineCode}`);
  });

  serverSocket.on('disconnect', () => {
    isConnected = false;
    usuarioActual = null;
    broadcast('status', { connected: false, code: machineCode, estado: 'apagado', msg: `Desconectado del servidor` });
    console.log('[SIM] Desconectado');
  });

  serverSocket.on('connect_error', (err) => {
    broadcast('status', { connected: false, code: machineCode, estado: 'apagado', msg: `Error: ${err.message} — ¿Está corriendo el servidor en ${SERVER_URL}?` });
  });

  serverSocket.on('usuario_vinculado', (data) => {
    usuarioActual = data;
    const lang     = data.idioma || 'es';
    const greeting = lang === 'en' ? `Hi, ${data.nombre}!` : `¡Hola, ${data.nombre}!`;
    broadcast('usuario_vinculado', { ...data, greeting });
    console.log('[SIM] Usuario vinculado:', greeting);
  });

  serverSocket.on('sesion_terminada', (data) => {
    usuarioActual = null;
    broadcast('sesion_terminada', data);
    console.log('[SIM] Sesión terminada:', data.motivo);
  });

  serverSocket.on('desconectado', (data) => {
    broadcast('status', { connected: false, code: machineCode, estado: 'apagado', msg: `Desconectado: ${data.motivo}` });
  });
}

// ── Socket UI → simulador ────────────────────────────
io.on('connection', (uiSocket) => {
  // Enviar estado actual al nuevo cliente
  uiSocket.emit('status', {
    connected: isConnected,
    code:      machineCode,
    estado:    isConnected ? 'disponible' : 'apagado',
    msg:       isConnected ? `✓ Conectado como ${machineCode}` : 'Esperando configuración...'
  });
  if (usuarioActual) uiSocket.emit('usuario_vinculado', { ...usuarioActual, greeting: usuarioActual.greeting || `¡Hola, ${usuarioActual.nombre}!` });

  // Configurar nombre y conectar
  uiSocket.on('set_device', ({ code }) => {
    if (!code || !code.trim()) return;
    connectToServer(code.trim());
  });

  // Push frames de cámara
  uiSocket.on('push_frame', ({ frame }) => {
    if (!serverSocket || !isConnected || !machineCode) return;
    serverSocket.emit('camera_frame_push', { frame, codigo: machineCode });
  });

  // Simular clasificación con tipo específico
  uiSocket.on('simular_clasificacion', ({ tipo }) => {
    if (!serverSocket || !isConnected) return;
    const materiales = {
      plastico:  { cat: 'PLASTICO',  mat: 'Plastic bottle',    xp: 15 },
      carton:    { cat: 'CARTON',    mat: 'Cardboard box',     xp: 12 },
      metal:     { cat: 'METAL',     mat: 'Aluminium can',     xp: 18 },
      vidrio:    { cat: 'VIDRIO',    mat: 'Glass jar',         xp: 20 },
      unicel:    { cat: 'UNICEL',    mat: 'Polystyrene cup',   xp: 10 },
      papel:     { cat: 'PAPEL',     mat: 'Paper sheet',       xp: 8  },
      baterias:  { cat: 'ESPECIAL',  mat: 'Battery',           xp: 25 },
      aleatorio: null
    };

    let item;
    if (tipo === 'aleatorio' || !materiales[tipo]) {
      const keys = Object.keys(materiales).filter(k => k !== 'aleatorio');
      item = materiales[keys[Math.floor(Math.random() * keys.length)]];
    } else {
      item = materiales[tipo];
    }

    const conf = 0.82 + Math.random() * 0.17;
    setTimeout(() => {
      serverSocket.emit('resultado_clasificacion', {
        codigo:    machineCode,
        material:  item.mat,
        categoria: item.cat,
        confianza: conf,
        xp_ganado: item.xp
      });
      broadcast('clasificacion_local', { categoria: item.cat, material: item.mat, conf, xp: item.xp });
      console.log(`[SIM] Clasificación: ${item.cat} (${(conf*100).toFixed(0)}%)`);
    }, 800 + Math.random() * 800);

    broadcast('clasificando', { tipo: item.cat });
  });

  // Parar sesión (botón touch Raspberry)
  uiSocket.on('parar_sesion', () => {
    if (!serverSocket || !isConnected) return;
    serverSocket.emit('parar_sesion', { codigo: machineCode });
    usuarioActual = null;
    broadcast('sesion_terminada', { motivo: 'maquina' });
  });

  // Cambiar estado manualmente
  uiSocket.on('cambiar_estado', ({ estado }) => {
    if (!serverSocket || !isConnected || !machineCode) return;
    serverSocket.emit('cambiar_estado', { codigo: machineCode, estado });
    broadcast('estado_cambiado', { estado });
  });

  // Desconectar del servidor
  uiSocket.on('desconectar_servidor', () => {
    if (serverSocket) serverSocket.disconnect();
    isConnected   = false;
    usuarioActual = null;
    machineCode   = null;
    broadcast('status', { connected: false, code: null, estado: 'apagado', msg: 'Desconectado manualmente' });
  });
});

// ── UI HTML ──────────────────────────────────────────
app.get('/', (req, res) => res.send(`<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ECO-SORT Simulador Raspberry Pi</title>
<style>
:root{
  --g:#00c27c;--gd:#009960;--gl:#00e89a;
  --bg:#0a1a10;--card:#0f2418;--card2:#132b1e;
  --border:rgba(0,194,124,0.18);--border2:rgba(0,194,124,0.08);
  --text:#e8f8f0;--text2:#6b9e84;--text3:#3d6b55;
}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:'Courier New',monospace;min-height:100vh;}
header{background:var(--card);border-bottom:1px solid var(--border);padding:1rem 1.5rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.8rem;}
.logo{color:var(--g);font-size:1.1rem;font-weight:700;letter-spacing:0.05em;}
.logo span{color:var(--text2);}
.status-badge{display:flex;align-items:center;gap:0.5rem;background:var(--card2);border:1px solid var(--border);border-radius:50px;padding:0.35rem 0.9rem;font-size:0.78rem;}
.dot{width:8px;height:8px;border-radius:50%;background:#ef4444;flex-shrink:0;transition:background 0.3s;}
.dot.on{background:var(--g);box-shadow:0 0 8px rgba(0,194,124,0.5);animation:pulse 1.5s infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.4;}}
.main{display:grid;grid-template-columns:1fr 1fr;gap:1rem;padding:1rem 1.5rem;max-width:960px;margin:0 auto;}
@media(max-width:640px){.main{grid-template-columns:1fr;}}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.2rem;}
.card h2{font-size:0.75rem;color:var(--g);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:1rem;display:flex;align-items:center;gap:0.4rem;}
.setup-row{display:flex;gap:0.6rem;margin-bottom:0.8rem;}
input[type=text]{flex:1;background:var(--card2);border:1.5px solid var(--border);color:var(--text);padding:0.6rem 0.8rem;border-radius:8px;font-family:'Courier New',monospace;font-size:0.9rem;outline:none;text-transform:uppercase;font-weight:700;letter-spacing:0.08em;}
input[type=text]:focus{border-color:var(--g);}
input[type=text]::placeholder{text-transform:none;font-weight:400;letter-spacing:0;}
button{background:linear-gradient(135deg,var(--g),var(--gl));color:#0a1a10;border:none;padding:0.6rem 1rem;border-radius:8px;font-family:'Courier New',monospace;font-size:0.8rem;font-weight:700;cursor:pointer;transition:all 0.2s;white-space:nowrap;}
button:hover:not(:disabled){filter:brightness(1.1);transform:translateY(-1px);}
button:disabled{opacity:0.35;cursor:not-allowed;transform:none;}
.btn-red{background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;}
.btn-yellow{background:linear-gradient(135deg,#f59e0b,#d97706);color:#0a1a10;}
.btn-gray{background:var(--card2);color:var(--text2);border:1px solid var(--border);}
.btn-gray:hover:not(:disabled){background:var(--border);color:var(--text);}
video{width:100%;border-radius:8px;border:1px solid var(--border);background:#000;aspect-ratio:16/9;margin-bottom:0.8rem;}
canvas{display:none;}
/* Botones de materiales */
.mat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;margin-bottom:0.8rem;}
@media(max-width:400px){.mat-grid{grid-template-columns:repeat(2,1fr);}}
.mat-btn{padding:0.5rem 0.3rem;font-size:0.72rem;border-radius:8px;text-align:center;}
.mat-plastic{background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);}
.mat-carton{background:rgba(180,100,30,0.15);color:#fbbf24;border:1px solid rgba(180,100,30,0.3);}
.mat-metal{background:rgba(148,163,184,0.15);color:#94a3b8;border:1px solid rgba(148,163,184,0.3);}
.mat-vidrio{background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);}
.mat-unicel{background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.3);}
.mat-papel{background:rgba(139,92,246,0.15);color:#a78bfa;border:1px solid rgba(139,92,246,0.3);}
.mat-baterias{background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);}
.mat-aleatorio{background:linear-gradient(135deg,rgba(0,194,124,0.15),rgba(0,168,230,0.15));color:var(--g);border:1px solid var(--border);}
.mat-btn:hover:not(:disabled){filter:brightness(1.3);}
/* User card */
.user-card{background:var(--card2);border:1px solid var(--border);border-radius:8px;padding:1rem;min-height:72px;display:flex;align-items:center;justify-content:center;margin-bottom:0.8rem;transition:all 0.3s;}
.user-card.linked{border-color:var(--g);background:rgba(0,194,124,0.08);}
/* Log */
.log{background:var(--card2);border:1px solid var(--border2);border-radius:8px;padding:0.7rem;height:160px;overflow-y:auto;font-size:0.72rem;}
.log::-webkit-scrollbar{width:3px;}
.log::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px;}
.log p{padding:0.12rem 0;border-bottom:1px solid var(--border2);display:flex;gap:0.5rem;}
.log p .ts{color:var(--text3);flex-shrink:0;}
.log p.ok .msg{color:var(--gl);}
.log p.err .msg{color:#f87171;}
.log p.info .msg{color:#60a5fa;}
.log p.warn .msg{color:#fbbf24;}
/* Estado badge */
.estado-row{display:flex;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.8rem;}
.estado-btn{font-size:0.7rem;padding:0.3rem 0.7rem;border-radius:50px;}
.clasif-flash{
  position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) scale(0);
  background:var(--card);border:2px solid var(--g);border-radius:16px;
  padding:1.5rem 2.5rem;text-align:center;z-index:999;
  transition:all 0.2s;pointer-events:none;
}
.clasif-flash.show{transform:translate(-50%,-50%) scale(1);}
.clasif-flash .cat{font-size:1.6rem;font-weight:700;color:var(--g);}
.clasif-flash .xp{font-size:1rem;color:#fbbf24;margin-top:0.3rem;}
</style>
</head>
<body>

<header>
  <div class="logo">🍓 ECO-SORT <span>Simulador Raspberry Pi</span></div>
  <div class="status-badge">
    <div class="dot" id="dot"></div>
    <span id="status-msg">Sin configurar</span>
  </div>
</header>

<div class="main">

  <!-- Configuración -->
  <div class="card">
    <h2>⚡ Dispositivo</h2>
    <div class="setup-row">
      <input type="text" id="device-code" placeholder="Nombre del dispositivo (ej: ECO-001)" maxlength="20">
      <button id="btn-set-device">Conectar</button>
    </div>
    <div style="font-size:0.72rem;color:var(--text2);margin-bottom:0.8rem;">
      Servidor: <span style="color:var(--g);">${SERVER_URL}</span>
    </div>

    <!-- Estado de la máquina -->
    <div style="font-size:0.72rem;color:var(--text2);margin-bottom:0.4rem;">Cambiar estado:</div>
    <div class="estado-row">
      <button class="estado-btn btn-gray" onclick="cambiarEstado('disponible')" id="btn-disponible">✓ Disponible</button>
      <button class="estado-btn btn-yellow" onclick="cambiarEstado('configurando')" id="btn-configurando">⚙ Configurando</button>
      <button class="estado-btn btn-red" onclick="cambiarEstado('en_uso')" id="btn-en_uso">🔴 En uso</button>
    </div>
    <button class="btn-red" id="btn-desconectar" disabled style="width:100%;margin-top:0.3rem;font-size:0.78rem;">⏹ Desconectar</button>

    <!-- Usuario vinculado -->
    <div style="font-size:0.72rem;color:var(--text2);margin:0.8rem 0 0.4rem;">Usuario vinculado:</div>
    <div class="user-card" id="user-card">
      <span style="color:var(--text3);font-size:0.78rem;">Esperando conexión de usuario...</span>
    </div>
    <button class="btn-red" id="btn-parar" disabled style="width:100%;font-size:0.78rem;">⏹ Parar sesión (botón touch)</button>
  </div>

  <!-- Cámara -->
  <div class="card">
    <h2>📷 Cámara</h2>
    <video id="video" autoplay muted playsinline></video>
    <canvas id="canvas"></canvas>
    <div style="display:flex;gap:0.5rem;margin-bottom:0.8rem;">
      <button id="btn-cam" style="flex:1;">Activar cámara</button>
      <button id="btn-stop-cam" class="btn-red" disabled style="flex:1;">Detener cam</button>
    </div>

    <!-- Botones de materiales -->
    <div style="font-size:0.72rem;color:var(--text2);margin-bottom:0.5rem;">Simular clasificación:</div>
    <div class="mat-grid">
      <button class="mat-btn mat-plastic" onclick="simular('plastico')" id="mb-0">♻ Plástico</button>
      <button class="mat-btn mat-carton"  onclick="simular('carton')"   id="mb-1">📦 Cartón</button>
      <button class="mat-btn mat-metal"   onclick="simular('metal')"    id="mb-2">🥫 Metal</button>
      <button class="mat-btn mat-vidrio"  onclick="simular('vidrio')"   id="mb-3">🫙 Vidrio</button>
      <button class="mat-btn mat-unicel"  onclick="simular('unicel')"   id="mb-4">🍶 Unicel</button>
      <button class="mat-btn mat-papel"   onclick="simular('papel')"    id="mb-5">📄 Papel</button>
      <button class="mat-btn mat-baterias" onclick="simular('baterias')" id="mb-6">🔋 Batería</button>
      <button class="mat-btn mat-aleatorio" onclick="simular('aleatorio')" id="mb-7">🎲 Random</button>
    </div>
  </div>

  <!-- Log — span completo -->
  <div class="card" style="grid-column:1/-1;">
    <h2>📋 Log de eventos</h2>
    <div class="log" id="log">
      <p class="info"><span class="ts">${new Date().toLocaleTimeString()}</span><span class="msg">Simulador iniciado. Configura el nombre del dispositivo y conecta.</span></p>
    </div>
  </div>

</div>

<!-- Flash clasificación -->
<div class="clasif-flash" id="clasif-flash">
  <div class="cat" id="flash-cat"></div>
  <div id="flash-mat" style="font-size:0.85rem;color:var(--text2);margin-top:0.2rem;"></div>
  <div class="xp" id="flash-xp"></div>
</div>

<script src="/socket.io/socket.io.js"></script>
<script>
const socket = io();
let camStream = null;
let streamInterval = null;
let connected = false;

// ── Status ──
socket.on('status', d => {
  document.getElementById('status-msg').textContent = d.msg;
  document.getElementById('dot').classList.toggle('on', d.connected);
  document.getElementById('btn-desconectar').disabled = !d.connected;
  document.getElementById('btn-parar').disabled = !d.connected;
  setMaterialButtons(d.connected);
  addLog(d.msg, d.connected ? 'ok' : 'err');
  connected = d.connected;
});

// ── Usuario vinculado ──
socket.on('usuario_vinculado', d => {
  document.getElementById('user-card').className = 'user-card linked';
  document.getElementById('user-card').innerHTML = \`
    <div style="text-align:center;">
      <div style="font-size:1.4rem;margin-bottom:0.3rem;">👤</div>
      <div style="font-size:1rem;font-weight:700;color:var(--g);">\${d.greeting}</div>
      <div style="font-size:0.7rem;color:var(--text2);margin-top:0.2rem;">ID: \${d.id} · \${d.idioma==='en'?'🇺🇸 EN':'🇲🇽 ES'}</div>
    </div>\`;
  addLog('Usuario vinculado: ' + d.greeting, 'ok');
  document.getElementById('btn-parar').disabled = false;
});

// ── Sesión terminada ──
socket.on('sesion_terminada', d => {
  document.getElementById('user-card').className = 'user-card';
  document.getElementById('user-card').innerHTML = '<span style="color:var(--text3);font-size:0.78rem;">Sesión terminada (' + d.motivo + '). Esperando...</span>';
  addLog('Sesión terminada: ' + d.motivo, 'warn');
});

// ── Clasificación flash ──
socket.on('clasificacion_local', d => {
  const flash = document.getElementById('clasif-flash');
  document.getElementById('flash-cat').textContent = d.categoria;
  document.getElementById('flash-mat').textContent = d.material;
  document.getElementById('flash-xp').textContent = '+' + d.xp + ' XP ⚡';
  flash.classList.add('show');
  setTimeout(() => flash.classList.remove('show'), 2000);
  addLog('Clasificación → ' + d.categoria + ' +' + d.xp + ' XP', 'ok');
});

socket.on('clasificando', d => {
  addLog('Clasificando ' + d.tipo + '...', 'info');
});

// ── Configurar dispositivo ──
document.getElementById('btn-set-device').onclick = () => {
  const code = document.getElementById('device-code').value.trim().toUpperCase();
  if (!code) { addLog('Ingresa un nombre de dispositivo', 'err'); return; }
  socket.emit('set_device', { code });
  addLog('Conectando como ' + code + '...', 'info');
};
document.getElementById('device-code').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('btn-set-device').click();
});

// ── Cámara ──
document.getElementById('btn-cam').onclick = async () => {
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video:{ width:640,height:480 }, audio:false });
    document.getElementById('video').srcObject = camStream;
    startStream();
    document.getElementById('btn-cam').disabled = true;
    document.getElementById('btn-stop-cam').disabled = false;
    addLog('Cámara activada y transmitiendo', 'ok');
  } catch(e) {
    addLog('Error cámara: ' + e.message, 'err');
  }
};

document.getElementById('btn-stop-cam').onclick = () => {
  stopStream();
  addLog('Transmisión de cámara detenida', 'warn');
};

function startStream() {
  if (streamInterval) return;
  const video  = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  canvas.width = 320; canvas.height = 240;
  const ctx = canvas.getContext('2d');
  streamInterval = setInterval(() => {
    if (!connected) return;
    ctx.drawImage(video, 0, 0, 320, 240);
    canvas.toBlob(blob => {
      if (!blob) return;
      const reader = new FileReader();
      reader.onload = e => socket.emit('push_frame', { frame: e.target.result.split(',')[1] });
      reader.readAsDataURL(blob);
    }, 'image/jpeg', 0.55);
  }, 250); // ~4fps
}

function stopStream() {
  if (streamInterval) { clearInterval(streamInterval); streamInterval = null; }
  if (camStream) { camStream.getTracks().forEach(t => t.stop()); camStream = null; }
  document.getElementById('video').srcObject = null;
  document.getElementById('btn-cam').disabled = false;
  document.getElementById('btn-stop-cam').disabled = true;
}

// ── Simular clasificación ──
function simular(tipo) {
  if (!connected) { addLog('Conecta al servidor primero', 'err'); return; }
  socket.emit('simular_clasificacion', { tipo });
}

// ── Cambiar estado ──
function cambiarEstado(estado) {
  if (!connected) { addLog('Conecta al servidor primero', 'err'); return; }
  socket.emit('cambiar_estado', { estado });
  addLog('Estado cambiado → ' + estado, 'info');
}

// ── Parar sesión ──
document.getElementById('btn-parar').onclick = () => {
  socket.emit('parar_sesion');
  addLog('Sesión parada manualmente', 'warn');
};

// ── Desconectar ──
document.getElementById('btn-desconectar').onclick = () => {
  stopStream();
  socket.emit('desconectar_servidor');
  addLog('Desconectado del servidor', 'warn');
  document.getElementById('user-card').className = 'user-card';
  document.getElementById('user-card').innerHTML = '<span style="color:var(--text3);font-size:0.78rem;">Sin usuario</span>';
};

function setMaterialButtons(enabled) {
  for (let i = 0; i < 8; i++) {
    const b = document.getElementById('mb-' + i);
    if (b) b.disabled = !enabled;
  }
}
setMaterialButtons(false);

// ── Log ──
function addLog(msg, type = '') {
  const log = document.getElementById('log');
  const p   = document.createElement('p');
  p.className = type;
  p.innerHTML = \`<span class="ts">\${new Date().toLocaleTimeString()}</span><span class="msg">\${msg}</span>\`;
  log.prepend(p);
  if (log.children.length > 80) log.lastChild.remove();
}
</script>
</body>
</html>`));

server.listen(SIM_PORT, () => {
  console.log(`\n🍓 ECO-SORT Simulador Raspberry Pi v2`);
  console.log(`   UI: http://localhost:${SIM_PORT}`);
  console.log(`   Servidor destino: ${SERVER_URL}`);
  console.log(`\nPasos:`);
  console.log(`   1. Corre el servidor: npm start`);
  console.log(`   2. Corre este simulador: node raspberry-sim.js`);
  console.log(`   3. Abre http://localhost:${SIM_PORT}`);
  console.log(`   4. Escribe el nombre del dispositivo (ej: ECO-001) y conecta`);
  console.log(`   5. Desde el dashboard vincula con ese mismo código\n`);
});
