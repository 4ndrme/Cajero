import os
import pg8000.native
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

def init_db():
    host = os.getenv("DB_HOST", "localhost").strip()
    database = os.getenv("DB_NAME", "CajeroDB").strip()
    user = os.getenv("DB_USER", "postgres").strip()
    password = os.getenv("DB_PASS", "").strip()
    port = int(os.getenv("DB_PORT", "5432"))

    # Conexión directa mediante pg8000 (evita fallos de codificación en Windows)
    conn = pg8000.native.Connection(
        user=user,
        host=host,
        port=port,
        database=database,
        password=password
    )

    # 1. Creación de Tablas
    conn.run("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            cedula VARCHAR(10) UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cuentas (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER REFERENCES clientes(id),
            numero_cuenta VARCHAR(20) UNIQUE NOT NULL,
            saldo DECIMAL(12, 2) NOT NULL DEFAULT 0.00 CHECK (saldo >= 0),
            estado VARCHAR(20) DEFAULT 'Activa'
        );

        CREATE TABLE IF NOT EXISTS tarjetas (
            id SERIAL PRIMARY KEY,
            cuenta_id INTEGER REFERENCES cuentas(id),
            numero_tarjeta VARCHAR(16) UNIQUE NOT NULL,
            pin_hash VARCHAR(255) NOT NULL,
            intentos_fallidos INTEGER DEFAULT 0,
            estado VARCHAR(20) DEFAULT 'Activa'
        );

        CREATE TABLE IF NOT EXISTS transacciones (
            id SERIAL PRIMARY KEY,
            cuenta_id INTEGER REFERENCES cuentas(id),
            tipo VARCHAR(20) NOT NULL,
            monto DECIMAL(12, 2) NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Inserción de Datos de Prueba Iniciales
    res = conn.run("SELECT COUNT(*) FROM clientes")
    if res[0][0] == 0:
        print("Insertando cliente y tarjeta de prueba...")
        
        row_cliente = conn.run("INSERT INTO clientes (nombre, cedula) VALUES ('Michael Prueba', '1712345678') RETURNING id")
        cliente_id = row_cliente[0][0]

        row_cuenta = conn.run("INSERT INTO cuentas (cliente_id, numero_cuenta, saldo) VALUES (:c_id, '1000000001', 500.00) RETURNING id", c_id=cliente_id)
        cuenta_id = row_cuenta[0][0]
        
        pin_hash = generate_password_hash('1234')
        conn.run("INSERT INTO tarjetas (cuenta_id, numero_tarjeta, pin_hash) VALUES (:q_id, '4000123456789010', :pin)", 
                 q_id=cuenta_id, pin=pin_hash)

    conn.close()
    print("Core Bancario inicializado correctamente.")

if __name__ == '__main__':
    init_db()