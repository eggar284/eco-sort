#!/usr/bin/env python3
# ══════════════════════════════════════════
#  ECO-SORT — Gestor de usuarios
#  Uso: python3 admin_usuarios.py
# ══════════════════════════════════════════

import os
import sys

# ── INSTALA mysql-connector si no está ────
try:
    import mysql.connector
except ImportError:
    os.system("pip3 install mysql-connector-python --break-system-packages -q")
    import mysql.connector

# ── COLORES ───────────────────────────────
G  = '\033[0;32m'
R  = '\033[0;31m'
Y  = '\033[1;33m'
B  = '\033[0;34m'
W  = '\033[0;37m'
NC = '\033[0m'

# ── CONFIGURACIÓN — edita si es necesario ─
DB_CONFIG = {
    'host':     os.environ.get('DB_HOST', 'localhost'),
    'user':     os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASS', ''),
    'database': os.environ.get('DB_NAME', 'ecosort'),
    'charset':  'utf8mb4'
}

def conectar():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as e:
        print(f"\n{R}[ERROR] No se pudo conectar a MySQL: {e}{NC}")
        print(f"{Y}Edita DB_CONFIG en este script con tus credenciales.{NC}\n")
        sys.exit(1)

def limpiar():
    os.system('clear' if os.name == 'posix' else 'cls')

def header():
    print(f"{G}╔══════════════════════════════════════════╗")
    print(f"║       ECO-SORT — Gestor de Usuarios      ║")
    print(f"╚══════════════════════════════════════════╝{NC}\n")

def ver_usuarios(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, nombre, apellido, email, pais, xp,
               total_reciclados,
               DATE_FORMAT(created_at, '%d/%m/%Y %H:%i') as fecha
        FROM usuarios
        ORDER BY id ASC
    """)
    usuarios = cur.fetchall()
    cur.close()

    if not usuarios:
        print(f"\n{Y}No hay usuarios registrados.{NC}\n")
        return []

    print(f"\n{B}{'#':<4} {'ID':<6} {'Nombre':<22} {'Email':<30} {'País':<6} {'XP':<6} {'Reciclados':<10} {'Registro'}{NC}")
    print("─" * 100)
    for i, u in enumerate(usuarios, 1):
        nombre_completo = f"{u['nombre']} {u['apellido'] or ''}".strip()
        print(f"{G}{i:<4}{NC} {str(u['id']):<6} {nombre_completo:<22} {u['email']:<30} {u['pais'] or '—':<6} {u['xp']:<6} {u['total_reciclados']:<10} {u['fecha']}")
    print(f"\n{W}Total: {len(usuarios)} usuario(s){NC}\n")
    return usuarios

def borrar_uno(conn):
    limpiar(); header()
    print(f"{Y}── Borrar usuario específico ──{NC}\n")
    usuarios = ver_usuarios(conn)
    if not usuarios:
        input("Presiona ENTER para volver...")
        return

    print(f"{R}Escribe el NÚMERO (#) del usuario a borrar (0 = cancelar):{NC}")
    try:
        opcion = int(input("  → "))
    except ValueError:
        print(f"{R}Opción inválida.{NC}")
        input("Presiona ENTER para volver...")
        return

    if opcion == 0:
        return
    if opcion < 1 or opcion > len(usuarios):
        print(f"{R}Número fuera de rango.{NC}")
        input("Presiona ENTER para volver...")
        return

    u = usuarios[opcion - 1]
    nombre_completo = f"{u['nombre']} {u['apellido'] or ''}".strip()

    print(f"\n{R}¿Seguro que quieres borrar a:{NC}")
    print(f"   Nombre: {Y}{nombre_completo}{NC}")
    print(f"   Email:  {Y}{u['email']}{NC}")
    print(f"   ID:     {Y}{u['id']}{NC}")
    print(f"\n{R}Esto borrará también todas sus clasificaciones.{NC}")
    confirm = input(f"\nEscribe {Y}SI{NC} para confirmar: ").strip().upper()

    if confirm != 'SI':
        print(f"\n{G}Cancelado.{NC}")
        input("Presiona ENTER para volver...")
        return

    try:
        cur = conn.cursor()
        # Borrar clasificaciones del usuario primero (FK)
        cur.execute("DELETE FROM clasificaciones WHERE usuario_id = %s", (u['id'],))
        clas_borradas = cur.rowcount
        # Borrar el usuario
        cur.execute("DELETE FROM usuarios WHERE id = %s", (u['id'],))
        conn.commit()
        cur.close()
        print(f"\n{G}✓ Usuario '{nombre_completo}' borrado correctamente.{NC}")
        print(f"{G}  ({clas_borradas} clasificaciones también eliminadas){NC}")
    except mysql.connector.Error as e:
        print(f"\n{R}[ERROR] {e}{NC}")

    input("\nPresiona ENTER para volver...")

def borrar_todos(conn):
    limpiar(); header()
    print(f"{R}╔══════════════════════════════════════════╗")
    print(f"║   ⚠️  BORRAR TODOS LOS USUARIOS  ⚠️       ║")
    print(f"╚══════════════════════════════════════════╝{NC}\n")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total FROM usuarios")
    total = cur.fetchone()[0]
    cur.close()

    if total == 0:
        print(f"{Y}No hay usuarios en la base de datos.{NC}\n")
        input("Presiona ENTER para volver...")
        return

    print(f"{R}Esto borrará PERMANENTEMENTE los {total} usuarios y TODAS sus clasificaciones.{NC}")
    print(f"{R}Esta acción NO se puede deshacer.{NC}\n")

    confirm1 = input(f"Escribe {Y}BORRAR TODO{NC} para continuar: ").strip()
    if confirm1 != 'BORRAR TODO':
        print(f"\n{G}Cancelado.{NC}")
        input("Presiona ENTER para volver...")
        return

    confirm2 = input(f"¿Estás ABSOLUTAMENTE seguro? Escribe {Y}SI{NC}: ").strip().upper()
    if confirm2 != 'SI':
        print(f"\n{G}Cancelado.{NC}")
        input("Presiona ENTER para volver...")
        return

    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM clasificaciones")
        clas = cur.rowcount
        cur.execute("DELETE FROM usuarios")
        users = cur.rowcount
        # Reinicia los auto-increment
        cur.execute("ALTER TABLE usuarios AUTO_INCREMENT = 1")
        cur.execute("ALTER TABLE clasificaciones AUTO_INCREMENT = 1")
        conn.commit()
        cur.close()
        print(f"\n{G}✓ {users} usuarios borrados.{NC}")
        print(f"{G}✓ {clas} clasificaciones borradas.{NC}")
        print(f"{G}✓ Auto-increment reiniciado.{NC}")
    except mysql.connector.Error as e:
        print(f"\n{R}[ERROR] {e}{NC}")

    input("\nPresiona ENTER para volver...")

def main():
    conn = conectar()

    while True:
        limpiar()
        header()

        # Mostrar conteo rápido
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM usuarios")
            total = cur.fetchone()[0]
            cur.close()
            print(f"  Base de datos: {G}ecosort{NC}  |  Usuarios registrados: {Y}{total}{NC}\n")
        except Exception:
            pass

        print(f"  {G}1{NC}  Ver lista de usuarios")
        print(f"  {G}2{NC}  Borrar un usuario específico")
        print(f"  {R}3{NC}  Borrar TODOS los usuarios")
        print(f"  {W}0{NC}  Salir\n")

        opcion = input("  Elige una opción: ").strip()

        if opcion == '1':
            limpiar(); header()
            ver_usuarios(conn)
            input("Presiona ENTER para volver...")
        elif opcion == '2':
            borrar_uno(conn)
        elif opcion == '3':
            borrar_todos(conn)
        elif opcion == '0':
            print(f"\n{G}Hasta luego.{NC}\n")
            conn.close()
            sys.exit(0)
        else:
            pass  # simplemente recarga el menú

if __name__ == '__main__':
    main()
