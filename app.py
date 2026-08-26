from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config, get_db_connection
from fpdf import FPDF
import io
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = 'tu_clave_secreta_super_segura'  # Indispensable para las sesiones

# Vista del formulario de registro
@app.route('/registro')
def registro():
    return render_template('registro.html')

# API Endpoint para registrar cliente, cuenta y tarjeta
@app.route('/api/registrar_tarjeta', methods=['POST'])
def registrar_tarjeta():
    data = request.get_json()
    nombre = data.get('nombre')
    cedula = data.get('cedula')
    numero_tarjeta = str(data.get('tarjeta', '')).strip()
    pin = str(data.get('pin', '')).strip()
    saldo_inicial = float(data.get('saldo', 100.00))

    if not nombre or not cedula or not numero_tarjeta or not pin:
        return jsonify({'success': False, 'message': 'Todos los campos son obligatorios.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Crear Cliente
        cur.execute(
            "INSERT INTO clientes (nombre, cedula) VALUES (%s, %s) RETURNING id",
            (nombre, cedula)
        )
        cliente_id = cur.fetchone()[0]

        # 2. Crear Cuenta
        numero_cuenta = f"CTA-{numero_tarjeta}"
        cur.execute(
            "INSERT INTO cuentas (cliente_id, numero_cuenta, saldo) VALUES (%s, %s, %s) RETURNING id", 
            (cliente_id, numero_cuenta, saldo_inicial)
        )
        cuenta_id = cur.fetchone()[0]

        # 3. Crear Tarjeta
        pin_hash = generate_password_hash(pin)
        cur.execute(
            "INSERT INTO tarjetas (cuenta_id, numero_tarjeta, pin_hash, estado, intentos_fallidos) VALUES (%s, %s, %s, 'Activa', 0)", 
            (cuenta_id, numero_tarjeta, pin_hash)
        )

        conn.commit()
        return jsonify({'success': True, 'message': '¡Tarjeta registrada e ingresada con éxito!'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Error BD: {str(e)}'}), 500
    finally:
        cur.close()
        conn.close()

# 1. Pantalla de Inicio (Ingresar Tarjeta)
@app.route('/')
def index():
    session.clear()
    return render_template('index.html')

# Vista de la pantalla para ingresar el PIN
@app.route('/pin')
def vista_pin():
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    return render_template('pin.html')

# 2. API Endpoint para validar si la tarjeta existe
@app.route('/api/validar_tarjeta', methods=['POST'])
def validar_tarjeta():
    data = request.get_json()
    numero_tarjeta = str(data.get('tarjeta', '')).strip()

    if not numero_tarjeta:
        return jsonify({'success': False, 'message': 'Ingrese un número de tarjeta.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT id, estado FROM tarjetas WHERE numero_tarjeta = %s", (numero_tarjeta,))
        tarjeta = cur.fetchone()

        if not tarjeta:
            return jsonify({'success': False, 'message': 'Tarjeta no encontrada. Regístrela primero.'}), 404

        if tarjeta[1] == 'Bloqueada':
            return jsonify({'success': False, 'message': 'La tarjeta se encuentra bloqueada.'}), 403

        # Guardamos unificada la sesión
        session['tarjeta_actual'] = numero_tarjeta
        return jsonify({'success': True, 'redirect': '/pin'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    finally:
        cur.close()
        conn.close()

# 4. API Endpoint Único para validar el PIN y manejar bloqueos
@app.route('/api/validar_pin', methods=['POST'])
def validar_pin():
    if 'tarjeta_actual' not in session:
        return jsonify({'success': False, 'message': 'Sesión expirada.'}), 401

    data = request.get_json()
    pin_ingresado = str(data.get('pin', '')).strip()
    numero_tarjeta = session['tarjeta_actual']

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT id, pin_hash, estado, intentos_fallidos FROM tarjetas WHERE numero_tarjeta = %s", (numero_tarjeta,))
        tarjeta_data = cur.fetchone()

        if not tarjeta_data:
            return jsonify({'success': False, 'message': 'Tarjeta no encontrada.'}), 404

        tarjeta_id, pin_hash, estado, intentos = tarjeta_data

        if estado == 'Bloqueada':
            return jsonify({'success': False, 'message': 'La tarjeta está bloqueada.'}), 403

        if check_password_hash(pin_hash, pin_ingresado):
            cur.execute("UPDATE tarjetas SET intentos_fallidos = 0 WHERE id = %s", (tarjeta_id,))
            conn.commit()
            
            session['autenticado'] = True
            return jsonify({'success': True, 'redirect': '/menu'})
        else:
            intentos += 1
            if intentos >= 3:
                cur.execute("UPDATE tarjetas SET intentos_fallidos = %s, estado = 'Bloqueada' WHERE id = %s", (intentos, tarjeta_id))
                conn.commit()
                session.clear()
                return jsonify({'success': False, 'message': 'PIN incorrecto. Su tarjeta ha sido bloqueada por seguridad.'}), 403
            else:
                cur.execute("UPDATE tarjetas SET intentos_fallidos = %s WHERE id = %s", (intentos, tarjeta_id))
                conn.commit()
                restantes = 3 - intentos
                return jsonify({'success': False, 'message': f'PIN incorrecto. Te quedan {restantes} intentos.'}), 400

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Error en servidor: {str(e)}'}), 500
    finally:
        cur.close()
        conn.close()

# 5. Pantalla del Menú Principal
@app.route('/menu')
def menu():
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    return render_template('menu.html')

# 6. Pantalla de Saldo y Movimientos
@app.route('/saldo_movimientos')
def saldo_movimientos():
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    
    numero_tarjeta = session['tarjeta_actual']
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT c.id, c.saldo 
        FROM cuentas c
        JOIN tarjetas t ON c.id = t.cuenta_id
        WHERE t.numero_tarjeta = %s
    """, (numero_tarjeta,))
    
    resultado = cur.fetchone()
    if not resultado:
        cur.close()
        conn.close()
        return redirect(url_for('index'))
        
    cuenta_id, saldo_actual = resultado
    
    cur.execute("INSERT INTO transacciones (cuenta_id, tipo, monto) VALUES (%s, 'Consulta', 0.00)", (cuenta_id,))
    conn.commit()
    
    cur.execute("""
        SELECT tipo, monto, fecha 
        FROM transacciones 
        WHERE cuenta_id = %s 
        ORDER BY fecha DESC 
        LIMIT 5
    """, (cuenta_id,))
    movimientos = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('saldo_movimientos.html', saldo=saldo_actual, movimientos=movimientos)

# 7. Generación de PDF con Movimientos
@app.route('/imprimir_movimientos')
def imprimir_movimientos():
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    
    numero_tarjeta = session['tarjeta_actual']
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT cl.nombre, c.numero_cuenta, c.saldo
        FROM clientes cl
        JOIN cuentas c ON cl.id = c.cliente_id
        JOIN tarjetas t ON c.id = t.cuenta_id
        WHERE t.numero_tarjeta = %s
    """, (numero_tarjeta,))
    cliente_info = cur.fetchone()
    
    cur.execute("""
        SELECT tipo, monto, fecha 
        FROM transacciones 
        WHERE cuenta_id = (SELECT cuenta_id FROM tarjetas WHERE numero_tarjeta = %s)
        ORDER BY fecha DESC
    """, (numero_tarjeta,))
    movimientos = cur.fetchall()
    
    cur.close()
    conn.close()

    if not cliente_info:
        return redirect(url_for('index'))

    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 18)
    pdf.set_text_color(25, 79, 43)
    pdf.cell(200, 10, txt="CajeBank", ln=True, align='C')
    
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(200, 10, txt="Estado de Cuenta y Movimientos", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 8, txt=f"Titular: {cliente_info[0]}", ln=True)
    pdf.cell(200, 8, txt=f"Nro. Cuenta: {cliente_info[1]}", ln=True)
    pdf.cell(200, 8, txt=f"Saldo Disponible: ${cliente_info[2]:.2f}", ln=True)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(27, 138, 71)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(60, 10, "Fecha", border=1, fill=True, align='C')
    pdf.cell(70, 10, "Tipo de Movimiento", border=1, fill=True, align='C')
    pdf.cell(60, 10, "Monto", border=1, fill=True, align='C')
    pdf.ln()
    
    pdf.set_font("Arial", size=11)
    pdf.set_text_color(0, 0, 0)
    for mov in movimientos:
        fecha_str = mov[2].strftime('%Y-%m-%d %H:%M')
        tipo = mov[0]
        monto = float(mov[1])
        monto_str = f"- ${monto:.2f}" if tipo == 'Retiro' else (f"+ ${monto:.2f}" if tipo == 'Deposito' else f"${monto:.2f}")
        
        pdf.cell(60, 10, fecha_str, border=1, align='C')
        pdf.cell(70, 10, tipo, border=1, align='C')
        pdf.cell(60, 10, monto_str, border=1, align='C')
        pdf.ln()

    pdf_output = pdf.output(dest='S').encode('latin1')
    return send_file(io.BytesIO(pdf_output), mimetype='application/pdf', as_attachment=True, download_name='CajeBank_Movimientos.pdf')

# 8. Pantalla de Retiro
@app.route('/retirar')
def retirar():
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    return render_template('retirar.html')

# 9. API Endpoint Transaccional de Retiro
@app.route('/api/procesar_retiro', methods=['POST'])
def procesar_retiro():
    if 'tarjeta_actual' not in session:
        return jsonify({'success': False, 'message': 'Sesión expirada.'}), 401
    
    data = request.get_json()
    monto_retiro = float(data.get('monto'))

    if monto_retiro <= 0 or monto_retiro % 5 != 0:
        return jsonify({'success': False, 'message': 'El monto a retirar debe ser múltiplo de $5.00.'}), 400

    numero_tarjeta = session['tarjeta_actual']
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT c.id, c.saldo 
            FROM cuentas c
            JOIN tarjetas t ON c.id = t.cuenta_id
            WHERE t.numero_tarjeta = %s
            FOR UPDATE
        """, (numero_tarjeta,))
        
        resultado = cur.fetchone()
        if not resultado:
            return jsonify({'success': False, 'message': 'Error de cuenta.'}), 404
            
        cuenta_id = resultado[0]
        saldo_actual = float(resultado[1])
        
        if saldo_actual < monto_retiro:
            return jsonify({'success': False, 'message': 'Fondos insuficientes para esta transacción.'}), 400
        
        nuevo_saldo = saldo_actual - monto_retiro
        
        cur.execute("UPDATE cuentas SET saldo = %s WHERE id = %s", (nuevo_saldo, cuenta_id))
        cur.execute("INSERT INTO transacciones (cuenta_id, tipo, monto) VALUES (%s, 'Retiro', %s)", (cuenta_id, monto_retiro))
        
        conn.commit()
        return jsonify({'success': True, 'message': f'Retiro exitoso de ${monto_retiro:.2f}. Retire su efectivo.'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Fallo del sistema. La transacción ha sido revertida.'}), 500
    finally:
        cur.close()
        conn.close()

# 10. Pantalla de Otro Valor
@app.route('/otro_valor')
def otro_valor():
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    return render_template('otro_valor.html')

# 11. Pantalla de Depósito
@app.route('/depositar')
def depositar():
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    return render_template('depositar.html')

# 12. API Endpoint Transaccional de Depósito
@app.route('/api/procesar_deposito', methods=['POST'])
def procesar_deposito():
    if 'tarjeta_actual' not in session:
        return jsonify({'success': False, 'message': 'Sesión expirada.'}), 401
    
    data = request.get_json()
    try:
        monto_deposito = float(data.get('monto'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Monto inválido.'}), 400

    if monto_deposito <= 0:
        return jsonify({'success': False, 'message': 'El monto a depositar debe ser mayor a $0.00.'}), 400

    numero_tarjeta = session['tarjeta_actual']
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT c.id, c.saldo 
            FROM cuentas c
            JOIN tarjetas t ON c.id = t.cuenta_id
            WHERE t.numero_tarjeta = %s
            FOR UPDATE
        """, (numero_tarjeta,))
        
        resultado = cur.fetchone()
        if not resultado:
            return jsonify({'success': False, 'message': 'Error de cuenta.'}), 404
            
        cuenta_id = resultado[0]
        saldo_actual = float(resultado[1])
        nuevo_saldo = saldo_actual + monto_deposito
        
        cur.execute("UPDATE cuentas SET saldo = %s WHERE id = %s", (nuevo_saldo, cuenta_id))
        cur.execute("INSERT INTO transacciones (cuenta_id, tipo, monto) VALUES (%s, 'Deposito', %s)", (cuenta_id, monto_deposito))
        
        conn.commit()
        return jsonify({'success': True, 'message': f'Depósito exitoso de ${monto_deposito:.2f}.'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Fallo del sistema. La transacción ha sido revertida.'}), 500
    finally:
        cur.close()
        conn.close()

# 15. Pantalla de Pago de Servicios
@app.route('/pagar_servicios')
def pagar_servicios():
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    return render_template('pagar_servicios.html')

# 16. API Endpoint Transaccional para Pago de Servicios
@app.route('/api/procesar_pago_servicio', methods=['POST'])
def procesar_pago_servicio():
    if 'tarjeta_actual' not in session:
        return jsonify({'success': False, 'message': 'Sesión expirada.'}), 401
    
    data = request.get_json()
    servicio = data.get('servicio')
    try:
        monto_pago = float(data.get('monto'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Monto inválido.'}), 400

    if monto_pago <= 0:
        return jsonify({'success': False, 'message': 'El monto a pagar debe ser mayor a $0.00.'}), 400

    numero_tarjeta = session['tarjeta_actual']
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT c.id, c.saldo 
            FROM cuentas c
            JOIN tarjetas t ON c.id = t.cuenta_id
            WHERE t.numero_tarjeta = %s
            FOR UPDATE
        """, (numero_tarjeta,))
        
        resultado = cur.fetchone()
        if not resultado:
            return jsonify({'success': False, 'message': 'Error de cuenta.'}), 404
            
        cuenta_id = resultado[0]
        saldo_actual = float(resultado[1])
        
        if saldo_actual < monto_pago:
            return jsonify({'success': False, 'message': 'Fondos insuficientes para pagar este servicio.'}), 400
        
        nuevo_saldo = saldo_actual - monto_pago
        tipo_movimiento = f"Pago {servicio}"[:20]
        
        cur.execute("UPDATE cuentas SET saldo = %s WHERE id = %s", (nuevo_saldo, cuenta_id))
        cur.execute("INSERT INTO transacciones (cuenta_id, tipo, monto) VALUES (%s, %s, %s)", (cuenta_id, tipo_movimiento, monto_pago))
        
        conn.commit()
        return jsonify({'success': True, 'message': f'Pago de {servicio} por ${monto_pago:.2f} procesado exitosamente.'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Fallo del sistema. Transacción revertida.'}), 500
    finally:
        cur.close()
        conn.close()

# 17. Generación de Comprobante de Pago de Servicio (PDF)
@app.route('/imprimir_recibo_servicio/<servicio>/<monto>')
def imprimir_recibo_servicio(servicio, monto):
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))

    numero_tarjeta = session['tarjeta_actual']
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT cl.nombre, c.numero_cuenta, c.saldo
        FROM clientes cl
        JOIN cuentas c ON cl.id = c.cliente_id
        JOIN tarjetas t ON c.id = t.cuenta_id
        WHERE t.numero_tarjeta = %s
    """, (numero_tarjeta,))
    cliente_info = cur.fetchone()
    cur.close()
    conn.close()

    if not cliente_info:
        return redirect(url_for('index'))

    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 18)
    pdf.set_text_color(25, 79, 43)
    pdf.cell(200, 10, txt="CajeBank", ln=True, align='C')
    
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(200, 10, txt="Comprobante de Pago de Servicio", ln=True, align='C')
    pdf.ln(10)
    
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 8, txt=f"Fecha y Hora: {fecha_actual}", ln=True)
    pdf.cell(200, 8, txt=f"Titular de la Cuenta: {cliente_info[0]}", ln=True)
    pdf.cell(200, 8, txt=f"Nro. de Cuenta: {cliente_info[1]}", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 8, txt=f"Servicio Pagado: {servicio}", ln=True)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(200, 8, txt=f"Monto Debitado: ${float(monto):.2f}", ln=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 8, txt=f"Saldo Disponible: ${cliente_info[2]:.2f}", ln=True)
    
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(200, 10, txt="Gracias por confiar en CajeBank. Tu cajero, tu aliado.", ln=True, align='C')

    pdf_output = pdf.output(dest='S').encode('latin1')
    return send_file(io.BytesIO(pdf_output), mimetype='application/pdf', as_attachment=True, download_name=f'Comprobante_{servicio}.pdf')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)