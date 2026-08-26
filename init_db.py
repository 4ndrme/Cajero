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
    db_key = os.getenv("DB_ENCRYPTION_KEY", "ClavePorDefecto123")

    conn = pg8000.native.Connection(
        user=user, host=host, port=port, database=database, password=password
    )

    print("Conectado. Activando seguridad nativa y recreando base de datos...")

    # Habilitar extensión pgcrypto
    conn.run("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    conn.run("DROP TABLE IF EXISTS transacciones CASCADE;")
    conn.run("DROP TABLE IF EXISTS tarjetas CASCADE;")
    conn.run("DROP TABLE IF EXISTS cuentas CASCADE;")
    conn.run("DROP TABLE IF EXISTS clientes CASCADE;")
    conn.run("DROP TABLE IF EXISTS cajero_estado CASCADE;")

    # El correo ahora es BYTEA para almacenar datos binarios encriptados
    conn.run("""
        CREATE TABLE clientes (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            cedula VARCHAR(10) UNIQUE NOT NULL,
            correo BYTEA NOT NULL 
        )
    """)
    
    conn.run("""
        CREATE TABLE cuentas (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER REFERENCES clientes(id),
            numero_cuenta VARCHAR(20) UNIQUE NOT NULL,
            saldo DECIMAL(12, 2) NOT NULL DEFAULT 0.00 CHECK (saldo >= 0),
            estado VARCHAR(20) DEFAULT 'Activa'
        )
    """)
    
    conn.run("""
        CREATE TABLE tarjetas (
            id SERIAL PRIMARY KEY,
            cuenta_id INTEGER REFERENCES cuentas(id),
            numero_tarjeta VARCHAR(16) UNIQUE NOT NULL,
            pin_hash VARCHAR(255) NOT NULL,
            intentos_fallidos INTEGER DEFAULT 0,
            estado VARCHAR(20) DEFAULT 'Activa'
        )
    """)
    
    conn.run("""
        CREATE TABLE transacciones (
            id SERIAL PRIMARY KEY,
            cuenta_id INTEGER REFERENCES cuentas(id),
            tipo VARCHAR(20) NOT NULL,
            monto DECIMAL(12, 2) NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.run("""
        CREATE TABLE cajero_estado (
            id SERIAL PRIMARY KEY,
            efectivo_disponible DECIMAL(12, 2) NOT NULL DEFAULT 0.00
        )
    """)

    # Bóveda
    conn.run("INSERT INTO cajero_estado (efectivo_disponible) VALUES (15000.00)") 

    # Insertar cliente usando PGP_SYM_ENCRYPT
    row_cliente = conn.run("""
        INSERT INTO clientes (nombre, cedula, correo) 
        VALUES ('Michael Prueba', '1712345678', PGP_SYM_ENCRYPT('michaelamigo29@gmailcom', :llave)) 
        RETURNING id
    """, llave=db_key)
    cliente_id = row_cliente[0][0]
    
    row_cuenta = conn.run("INSERT INTO cuentas (cliente_id, numero_cuenta, saldo) VALUES (:c_id, '1000000001', 500.00) RETURNING id", c_id=cliente_id)
    cuenta_id = row_cuenta[0][0]
    
    pin_hash = generate_password_hash('1234')
    conn.run("INSERT INTO tarjetas (cuenta_id, numero_tarjeta, pin_hash) VALUES (:q_id, '4000123456789010', :pin)", q_id=cuenta_id, pin=pin_hash)

    conn.close()
    print("¡Base de datos lista! Encriptación nativa activada.")

if __name__ == '__main__':
    init_db()