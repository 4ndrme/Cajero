import os
import psycopg2
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Cargar variables del archivo .env
load_dotenv()

def init_db():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS")
    )
    cur = conn.cursor()

    # 1. Creación de Tablas con Integridad Referencial
    cur.execute("""
        -- Tabla de Clientes
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            cedula VARCHAR(10) UNIQUE NOT NULL
        );

        -- Tabla de Cuentas (Integridad: el saldo NUNCA puede ser menor a 0)
        CREATE TABLE IF NOT EXISTS cuentas (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER REFERENCES clientes(id),
            numero_cuenta VARCHAR(20) UNIQUE NOT NULL,
            saldo DECIMAL(12, 2) NOT NULL DEFAULT 0.00 CHECK (saldo >= 0),
            estado VARCHAR(20) DEFAULT 'Activa'
        );

        -- Tabla de Tarjetas (PIN encriptado y control de bloqueos)
        CREATE TABLE IF NOT EXISTS tarjetas (
            id SERIAL PRIMARY KEY,
            cuenta_id INTEGER REFERENCES cuentas(id),
            numero_tarjeta VARCHAR(16) UNIQUE NOT NULL,
            pin_hash VARCHAR(255) NOT NULL,
            intentos_fallidos INTEGER DEFAULT 0,
            estado VARCHAR(20) DEFAULT 'Activa' -- Puede cambiar a 'Bloqueada'
        );

        -- Tabla de Historial (Auditoría inmutable)
        CREATE TABLE IF NOT EXISTS transacciones (
            id SERIAL PRIMARY KEY,
            cuenta_id INTEGER REFERENCES cuentas(id),
            tipo VARCHAR(20) NOT NULL, -- Retiro, Deposito, Consulta
            monto DECIMAL(12, 2) NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Inserción de Datos de Prueba Iniciales
    cur.execute("SELECT COUNT(*) FROM clientes")
    if cur.fetchone()[0] == 0:
        print("Insertando cliente y tarjeta de prueba...")
        
        # Crear un cliente
        cur.execute("INSERT INTO clientes (nombre, cedula) VALUES ('Michael Prueba', '1712345678') RETURNING id")
        cliente_id = cur.fetchone()[0]

        # Crearle una cuenta con $500 de saldo inicial
        cur.execute("INSERT INTO cuentas (cliente_id, numero_cuenta, saldo) VALUES (%s, '1000000001', 500.00) RETURNING id", (cliente_id,))
        cuenta_id = cur.fetchone()[0]
        # Crear una tarjeta para esa cuenta (PIN: 1234)
        pin_hash = generate_password_hash('1234')
        cur.execute("INSERT INTO tarjetas (cuenta_id, numero_tarjeta, pin_hash) VALUES (%s, %s, %s)", 
                    (cuenta_id, '4000123456789010', pin_hash))
    conn.commit()
    cur.close()
    conn.close()
    print("Core Bancario inicializado correctamente.")

if __name__ == '__main__':
    init_db()