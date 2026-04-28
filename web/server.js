// ══════════════════════════════════════════════════════
//  ECO-SORT — Backend Server v4
//  Cambios v4:
//    - Estados de máquina: disponible/en_uso/apagado/configurando
//    - Solo conexión si estado = 'disponible' Y socket activo
//    - Un usuario por máquina (seguridad real)
//    - Fix stats query (sin subquery anidada)
//    - Desconexión limpia notifica al dashboard
//    - Timer inactividad 3 min por objeto clasificado
// ══════════════════════════════════════════════════════

const express  = require('express');
const http     = require('http');
const socketio = require('socket.io');
const mysql    = require('mysql2/promise');
const bcrypt   = require('bcryptjs');
const jwt      = require('jsonwebtoken');
const path     = require('path');
const cors     = require('cors');
require('dotenv').config();

const app    = express();
const server = http.createServer(app);
const io     = socketio(server, {
  cors: { origin: '*', methods: ['GET','POST'] },
  maxHttpBufferSize: 5e6
});

const PORT            = process.env.PORT || 3000;
const JWT_SECRET      = process.env.JWT_SECRET || 'ecosort-secret-change-in-prod';
const SESSION_TIMEOUT = 3 * 60 * 1000;

// ─── DATABASE ─────────────────────────────────────────
let db;
async function connectDB() {
  db = await mysql.createPool({
    host:             process.env.DB_HOST || 'localhost',
    user:             process.env.DB_USER || 'root',
    password:         process.env.DB_PASS || '',
    database:         process.env.DB_NAME || 'ecosort',
    waitForConnections: true,
    connectionLimit:  10,
  });
  console.log('[DB] MySQL conectado');

  await db.execute(`CREATE TABLE IF NOT EXISTS usuarios (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    nombre           VARCHAR(100) NOT NULL,
    apellido         VARCHAR(100) DEFAULT '',
    email            VARCHAR(150) UNIQUE NOT NULL,
    password         VARCHAR(255) NOT NULL,
    pais             VARCHAR(10)  DEFAULT '',
    idioma           VARCHAR(5)   DEFAULT 'es',
    foto             LONGTEXT     DEFAULT NULL,
    xp               INT          DEFAULT 0,
    total_reciclados INT          DEFAULT 0,
    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
  )`);

  await db.execute(`CREATE TABLE IF NOT EXISTS clasificaciones (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id         INT,
    material_detectado VARCHAR(100),
    categoria          VARCHAR(50),
    confianza          FLOAT,
    xp_ganado          INT,
    codigo_maquina     VARCHAR(20),
    fecha              DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
  )`);

  // estado: 'apagado' | 'configurando' | 'disponible' | 'en_uso'
  await db.execute(`CREATE TABLE IF NOT EXISTS maquinas (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    codigo      VARCHAR(20) UNIQUE NOT NULL,
    socket_id   VARCHAR(100),
    usuario_id  INT DEFAULT NULL,
    estado      VARCHAR(20) DEFAULT 'apagado',
    last_seen   DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);

  console.log('[DB] Tablas listas');
}

// ─── MIDDLEWARE ───────────────────────────────────────
app.use(cors());
app.use(express.json({ limit: '15mb' }));
app.use(express.static(path.join(__dirname, 'public')));

function auth(req, res, next) {
  const h = req.headers.authorization;
  if (!h) return res.status(401).json({ message: 'Sin token' });
  try { req.user = jwt.verify(h.split(' ')[1], JWT_SECRET); next(); }
  catch(e) { res.status(401).json({ message: 'Token inválido' }); }
}

// ─── AUTH ─────────────────────────────────────────────
app.post('/api/auth/register', async (req, res) => {
  const { nombre, apellido, email, password, pais, idioma } = req.body;
  if (!nombre || !email || !password)
    return res.status(400).json({ message: 'Nombre, email y contraseña son requeridos' });
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))
    return res.status(400).json({ message: 'Formato de email inválido' });
  if (password.length < 6)
    return res.status(400).json({ message: 'Contraseña muy corta (mínimo 6 caracteres)' });
  try {
    const hash = await bcrypt.hash(password, 10);
    const [r] = await db.execute(
      'INSERT INTO usuarios (nombre,apellido,email,password,pais,idioma) VALUES (?,?,?,?,?,?)',
      [nombre, apellido||'', email, hash, pais||'', idioma||'es']
    );
    const user = { id: r.insertId, nombre, apellido: apellido||'', email, xp: 0, pais: pais||'', idioma: idioma||'es' };
    res.json({ token: jwt.sign(user, JWT_SECRET, { expiresIn: '7d' }), user });
  } catch(e) {
    if (e.code === 'ER_DUP_ENTRY') return res.status(409).json({ message: 'El email ya está registrado' });
    res.status(500).json({ message: 'Error del servidor' });
  }
});

app.post('/api/auth/login', async (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) return res.status(400).json({ message: 'Email y contraseña requeridos' });
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return res.status(400).json({ message: 'Email inválido' });
  try {
    const [rows] = await db.execute('SELECT * FROM usuarios WHERE email=?', [email]);
    if (!rows.length) return res.status(401).json({ message: 'Credenciales incorrectas' });
    const u = rows[0];
    if (!await bcrypt.compare(password, u.password)) return res.status(401).json({ message: 'Credenciales incorrectas' });
    const user = { id: u.id, nombre: u.nombre, apellido: u.apellido, email: u.email, xp: u.xp, pais: u.pais, idioma: u.idioma };
    res.json({ token: jwt.sign(user, JWT_SECRET, { expiresIn: '7d' }), user });
  } catch(e) { console.error('[LOGIN]', e.message); res.status(500).json({ message: 'Error del servidor' }); }
});

// ─── USER ─────────────────────────────────────────────
app.get('/api/user/me', auth, async (req, res) => {
  try {
    const [r] = await db.execute(
      'SELECT id,nombre,apellido,email,xp,pais,idioma,total_reciclados FROM usuarios WHERE id=?', [req.user.id]
    );
    if (!r.length) return res.status(404).json({ message: 'No encontrado' });
    res.json({ user: r[0] });
  } catch(e) { res.status(500).json({ message: 'Error' }); }
});

app.get('/api/user/photo', auth, async (req, res) => {
  try {
    const [r] = await db.execute('SELECT foto FROM usuarios WHERE id=?', [req.user.id]);
    res.json({ foto: r[0]?.foto || null });
  } catch(e) { res.status(500).json({ message: 'Error' }); }
});

app.post('/api/user/photo', auth, async (req, res) => {
  try {
    await db.execute('UPDATE usuarios SET foto=? WHERE id=?', [req.body.photo||null, req.user.id]);
    res.json({ success: true });
  } catch(e) { res.status(500).json({ message: 'Error' }); }
});

// Stats — dos queries separadas para evitar error subquery
app.get('/api/user/stats', auth, async (req, res) => {
  try {
    const [rows] = await db.execute('SELECT xp, total_reciclados FROM usuarios WHERE id=?', [req.user.id]);
    if (!rows.length) return res.json({ xp: 0, total_reciclados: 0, rank: 1 });
    const { xp, total_reciclados } = rows[0];
    const [rk] = await db.execute('SELECT COUNT(*) as cnt FROM usuarios WHERE xp > ?', [xp]);
    res.json({ xp, total_reciclados, rank: (rk[0]?.cnt || 0) + 1 });
  } catch(e) { console.error('[STATS]', e.message); res.status(500).json({ message: 'Error' }); }
});

app.get('/api/user/history', auth, async (req, res) => {
  try {
    const [r] = await db.execute(
      'SELECT * FROM clasificaciones WHERE usuario_id=? ORDER BY fecha DESC LIMIT 50', [req.user.id]
    );
    res.json({ registros: r });
  } catch(e) { res.status(500).json({ message: 'Error' }); }
});

app.get('/api/leaderboard', async (req, res) => {
  try {
    const [r] = await db.execute('SELECT nombre,xp,total_reciclados,foto FROM usuarios ORDER BY xp DESC LIMIT 10');
    res.json({ users: r });
  } catch(e) { res.status(500).json({ message: 'Error' }); }
});

// ─── MACHINE ──────────────────────────────────────────

// GET /api/machine/status/:codigo
app.get('/api/machine/status/:codigo', async (req, res) => {
  const { codigo } = req.params;
  try {
    const [rows] = await db.execute('SELECT estado, usuario_id FROM maquinas WHERE codigo=?', [codigo]);
    const socketActivo = activeMachines.has(codigo);
    if (!rows.length || !socketActivo) return res.json({ found: false, estado: 'apagado', en_uso: false });
    res.json({ found: true, estado: rows[0].estado, en_uso: rows[0].usuario_id !== null });
  } catch(e) { res.status(500).json({ message: 'Error' }); }
});

// POST /api/machine/link
app.post('/api/machine/link', auth, async (req, res) => {
  const { codigo } = req.body;
  if (!codigo) return res.status(400).json({ message: 'Código requerido' });
  try {
    // La máquina debe tener socket activo
    if (!activeMachines.has(codigo)) {
      return res.json({ success: false, message: 'Máquina no conectada o apagada. Verifica que el simulador/Raspberry esté encendida.' });
    }

    const [rows] = await db.execute('SELECT * FROM maquinas WHERE codigo=?', [codigo]);
    if (!rows.length) return res.json({ success: false, message: 'Código no registrado en el sistema.' });

    const maq = rows[0];
    const mensajes = {
      en_uso:       'La máquina ya está siendo usada por otro usuario.',
      configurando: 'La máquina está iniciando, espera unos segundos.',
      apagado:      'La máquina está apagada.',
    };
    if (maq.estado !== 'disponible') {
      return res.json({ success: false, message: mensajes[maq.estado] || 'Máquina no disponible.' });
    }

    await db.execute("UPDATE maquinas SET usuario_id=?, estado='en_uso' WHERE codigo=?", [req.user.id, codigo]);

    const [uRows] = await db.execute('SELECT nombre,apellido,idioma FROM usuarios WHERE id=?', [req.user.id]);
    const u = uRows[0] || {};
    const machSock = activeMachines.get(codigo);
    if (machSock) {
      io.to(machSock).emit('usuario_vinculado', {
        nombre:   u.nombre   || req.user.nombre,
        apellido: u.apellido || '',
        idioma:   u.idioma   || 'es',
        id:       req.user.id
      });
    }
    resetTimer(codigo);
    res.json({ success: true });
  } catch(e) { console.error('[LINK]', e.message); res.status(500).json({ message: 'Error' }); }
});

// POST /api/machine/unlink
app.post('/api/machine/unlink', auth, async (req, res) => {
  const { codigo } = req.body;
  try {
    await db.execute("UPDATE maquinas SET usuario_id=NULL, estado='disponible' WHERE codigo=? AND usuario_id=?",
      [codigo, req.user.id]);
    clearTimer(codigo);
    const machSock = activeMachines.get(codigo);
    if (machSock) io.to(machSock).emit('sesion_terminada', { motivo: 'usuario' });
    res.json({ success: true });
  } catch(e) { res.status(500).json({ message: 'Error' }); }
});

// POST /api/frame — Raspberry HTTP push
app.post('/api/frame', (req, res) => {
  const codigo = req.headers['x-machine-code'] || 'ECO-001';
  const chunks = [];
  req.on('data', c => chunks.push(c));
  req.on('end', () => {
    io.to(`machine:${codigo}`).emit('camera_frame', { frame: Buffer.concat(chunks).toString('base64') });
    res.sendStatus(200);
  });
});

// POST /api/clasificacion — Raspberry HTTP push
app.post('/api/clasificacion', async (req, res) => {
  const codigo = req.headers['x-machine-code'] || req.body.codigo;
  const { material, categoria, confianza, xp_ganado } = req.body;
  try {
    const [maq] = await db.execute('SELECT usuario_id FROM maquinas WHERE codigo=?', [codigo]);
    if (!maq.length || !maq[0].usuario_id)
      return res.status(400).json({ message: 'Sin usuario vinculado' });
    const uid = maq[0].usuario_id;
    const xp  = parseInt(xp_ganado) || 10;
    await db.execute(
      `INSERT INTO clasificaciones (usuario_id,material_detectado,categoria,confianza,xp_ganado,codigo_maquina) VALUES (?,?,?,?,?,?)`,
      [uid, material, categoria, confianza, xp, codigo]
    );
    await db.execute('UPDATE usuarios SET xp=xp+?, total_reciclados=total_reciclados+1 WHERE id=?', [xp, uid]);
    const [uR] = await db.execute('SELECT nombre,apellido,idioma FROM usuarios WHERE id=?', [uid]);
    const u = uR[0] || {};
    const payload = { material, categoria, confianza, xp_ganado: xp, codigo,
                      user_nombre: u.nombre, user_apellido: u.apellido, user_idioma: u.idioma };
    io.to(`machine:${codigo}`).emit('clasificacion_resultado', payload);
    resetTimer(codigo);
    res.json({ success: true });
  } catch(e) { console.error('[CLASIF]', e.message); res.status(500).json({ message: 'Error' }); }
});

// ─── TIMERS ───────────────────────────────────────────
const inactivityTimers = new Map();

function resetTimer(codigo) {
  clearTimer(codigo);
  const t = setTimeout(async () => {
    console.log(`[TIMER] Inactividad 3min → ${codigo}`);
    try { await db.execute("UPDATE maquinas SET usuario_id=NULL, estado='disponible' WHERE codigo=?", [codigo]); } catch(e) {}
    io.to(`machine:${codigo}`).emit('sesion_terminada', { motivo: 'inactividad' });
  }, SESSION_TIMEOUT);
  inactivityTimers.set(codigo, t);
}

function clearTimer(codigo) {
  if (inactivityTimers.has(codigo)) {
    clearTimeout(inactivityTimers.get(codigo));
    inactivityTimers.delete(codigo);
  }
}

// ─── SOCKET.IO ────────────────────────────────────────
const activeMachines = new Map();

io.on('connection', (socket) => {
  console.log('[SOCKET] Conectado:', socket.id);

  // Raspberry / Simulador se registra
  socket.on('registrar_maquina', async ({ codigo, estado_inicial }) => {
    console.log(`[SOCKET] Máquina ${codigo} registrada`);

    // Desconectar socket previo si existe
    const prevId = activeMachines.get(codigo);
    if (prevId && prevId !== socket.id) {
      const prev = io.sockets.sockets.get(prevId);
      if (prev) { prev.emit('desconectado', { motivo: 'nueva_conexion' }); prev.disconnect(true); }
    }

    activeMachines.set(codigo, socket.id);
    socket.join(`machine:${codigo}`);
    socket.data.codigoMaquina = codigo;

    const estado = estado_inicial || 'disponible';
    try {
      await db.execute(
        `INSERT INTO maquinas (codigo,socket_id,estado) VALUES (?,?,?)
         ON DUPLICATE KEY UPDATE socket_id=?, estado=?, last_seen=NOW()`,
        [codigo, socket.id, estado, socket.id, estado]
      );
    } catch(e) { console.error('[DB reg]', e.message); }

    io.emit('machine_state_change', { codigo, estado });
  });

  // Cambio de estado desde Raspberry
  socket.on('cambiar_estado', async ({ codigo: cod, estado }) => {
    const codigo = cod || socket.data.codigoMaquina;
    if (!codigo || !estado) return;
    try { await db.execute('UPDATE maquinas SET estado=? WHERE codigo=?', [estado, codigo]); } catch(e) {}
    io.emit('machine_state_change', { codigo, estado });
  });

  // Web se une al room
  socket.on('vincular_usuario', async ({ codigo, usuario }) => {
    socket.join(`machine:${codigo}`);
    const machSock = activeMachines.get(codigo);
    if (machSock) {
      let idioma = usuario.idioma || 'es';
      try {
        const [r] = await db.execute('SELECT idioma FROM usuarios WHERE id=?', [usuario.id]);
        if (r.length) idioma = r[0].idioma;
      } catch(e) {}
      io.to(machSock).emit('usuario_vinculado', { nombre: usuario.nombre, apellido: usuario.apellido||'', idioma, id: usuario.id });
    }
    resetTimer(codigo);
  });

  // Frames de cámara
  socket.on('camera_frame_push', ({ codigo, frame }) => {
    io.to(`machine:${codigo}`).emit('camera_frame', { frame });
    // No resetear timer aquí — solo se resetea con clasificaciones
  });

  // Resultado clasificación vía socket
  socket.on('resultado_clasificacion', async (data) => {
    const codigo = data.codigo || socket.data.codigoMaquina;
    try {
      const [maq] = await db.execute('SELECT usuario_id FROM maquinas WHERE codigo=?', [codigo]);
      if (maq.length && maq[0].usuario_id) {
        const uid = maq[0].usuario_id;
        const xp  = parseInt(data.xp_ganado) || 10;
        await db.execute(
          `INSERT INTO clasificaciones (usuario_id,material_detectado,categoria,confianza,xp_ganado,codigo_maquina) VALUES (?,?,?,?,?,?)`,
          [uid, data.material, data.categoria, data.confianza, xp, codigo]
        );
        await db.execute('UPDATE usuarios SET xp=xp+?, total_reciclados=total_reciclados+1 WHERE id=?', [xp, uid]);
        const [uR] = await db.execute('SELECT nombre,apellido,idioma FROM usuarios WHERE id=?', [uid]);
        if (uR.length) { data.user_nombre = uR[0].nombre; data.user_apellido = uR[0].apellido; data.user_idioma = uR[0].idioma; }
      }
    } catch(e) { console.error('[DB clasif]', e.message); }
    data.codigo = codigo;
    io.to(`machine:${codigo}`).emit('clasificacion_resultado', data);
    resetTimer(codigo);
  });

  // Parar sesión desde pantalla touch Raspberry
  socket.on('parar_sesion', async ({ codigo: cod } = {}) => {
    const codigo = cod || socket.data.codigoMaquina;
    if (!codigo) return;
    try { await db.execute("UPDATE maquinas SET usuario_id=NULL, estado='disponible' WHERE codigo=?", [codigo]); } catch(e) {}
    clearTimer(codigo);
    io.to(`machine:${codigo}`).emit('sesion_terminada', { motivo: 'maquina' });
    console.log(`[SOCKET] Sesión parada: ${codigo}`);
  });

  // Desconexión
  socket.on('disconnect', async () => {
    const codigo = socket.data.codigoMaquina;
    if (codigo && activeMachines.get(codigo) === socket.id) {
      activeMachines.delete(codigo);
      clearTimer(codigo);
      try {
        await db.execute("UPDATE maquinas SET estado='apagado', usuario_id=NULL, socket_id=NULL WHERE codigo=?", [codigo]);
      } catch(e) {}
      io.emit('machine_state_change', { codigo, estado: 'apagado' });
      io.to(`machine:${codigo}`).emit('sesion_terminada', { motivo: 'maquina_desconectada' });
      console.log(`[SOCKET] Máquina desconectada: ${codigo}`);
    }
  });
});

app.get('*', (req, res) => res.sendFile(path.join(__dirname, 'public', 'index.html')));

connectDB().then(() => {
  server.listen(PORT, () => {
    console.log(`\n🌱 ECO-SORT Server v4 → http://localhost:${PORT}\n`);
  });
}).catch(err => { console.error('[ERROR] MySQL:', err.message); process.exit(1); });
