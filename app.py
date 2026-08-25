from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash
from config import Config, get_db_connection
from fpdf import FPDF
import io
from flask import send_file
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

# 1. Pantalla de Inicio (Ingresar Tarjeta)
@app.route('/')
def index():
    # Limpiamos cualquier sesión previa al volver al inicio
    session.clear()
    return render_template('index.html')

# 2. API Endpoint para validar si la tarjeta existe
@app.route('/api/validar_tarjeta', methods=['POST'])
def validar_tarjeta():
    data = request.get_json()
    numero_tarjeta = data.get('tarjeta')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, estado FROM tarjetas WHERE numero_tarjeta = %s", (numero_tarjeta,))
    tarjeta = cur.fetchone()
    cur.close()
    conn.close()

    if tarjeta:
        if tarjeta[1] == 'Bloqueada':
            return jsonify({'success': False, 'message': 'Tarjeta bloqueada. Contacte a su banco.'}), 403
        
        # Guardamos el número de tarjeta temporalmente
        session['tarjeta_actual'] = numero_tarjeta
        return jsonify({'success': True, 'redirect': '/pin'})
    else:
        return jsonify({'success': False, 'message': 'Tarjeta no reconocida.'}), 404

# 3. Pantalla de Ingreso de PIN
@app.route('/pin')
def pin():
    # Seguridad: expulsa al usuario si no hay tarjeta validada
    if 'tarjeta_actual' not in session:
        return redirect(url_for('index'))
    return render_template('pin.html')

# 4. API Endpoint para validar el PIN y manejar bloqueos
@app.route('/api/validar_pin', methods=['POST'])
def validar_pin():
    if 'tarjeta_actual' not in session:
        return jsonify({'success': False, 'message': 'Sesión expirada.'}), 401

    data = request.get_json()
    pin_ingresado = data.get('pin')
    numero_tarjeta = session['tarjeta_actual']

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, pin_hash, intentos_fallidos FROM tarjetas WHERE numero_tarjeta = %s", (numero_tarjeta,))
    tarjeta = cur.fetchone()

    if not tarjeta:
        return jsonify({'success': False, 'message': 'Error interno del servidor.'}), 500

    tarjeta_id, pin_hash, intentos = tarjeta

    # Comparamos el PIN ingresado con el Hash
    if check_password_hash(pin_hash, pin_ingresado):
        cur.execute("UPDATE tarjetas SET intentos_fallidos = 0 WHERE id = %s", (tarjeta_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'redirect': '/menu'})
    else:
        intentos += 1
        if intentos >= 3:
            # Bloqueo al tercer intento fallido
            cur.execute("UPDATE tarjetas SET estado = 'Bloqueada', intentos_fallidos = %s WHERE id = %s", (intentos, tarjeta_id))
            conn.commit()
            cur.close()
            conn.close()
            session.clear() 
            return jsonify({'success': False, 'message': 'Demasiados intentos. Tarjeta BLOQUEADA por seguridad.'}), 403
        else:
            # Actualización del contador de intentos
            cur.execute("UPDATE tarjetas SET intentos_fallidos = %s WHERE id = %s", (intentos, tarjeta_id))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': f'PIN incorrecto. Intentos restantes: {3 - intentos}'}), 401

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
    
    # 1. Obtener ID de cuenta y saldo
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
    
    # 2. Registrar la consulta como una transacción (Auditoría)
    cur.execute("INSERT INTO transacciones (cuenta_id, tipo, monto) VALUES (%s, 'Consulta', 0.00)", (cuenta_id,))
    conn.commit()
    
    # 3. Obtener los últimos 5 movimientos
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
    
    # Obtener datos del cliente y su saldo
    cur.execute("""
        SELECT cl.nombre, c.numero_cuenta, c.saldo
        FROM clientes cl
        JOIN cuentas c ON cl.id = c.cliente_id
        JOIN tarjetas t ON c.id = t.cuenta_id
        WHERE t.numero_tarjeta = %s
    """, (numero_tarjeta,))
    cliente_info = cur.fetchone()
    
    # Obtener el historial completo de movimientos
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

    # --- CREACIÓN DEL PDF CON FPDF ---
    pdf = FPDF()
    pdf.add_page()
    
    # Cabecera Corporativa
    pdf.set_font("Arial", 'B', 18)
    pdf.set_text_color(25, 79, 43) # Verde CajeBank (#194f2b)
    pdf.cell(200, 10, txt="CajeBank", ln=True, align='C')
    
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(200, 10, txt="Estado de Cuenta y Movimientos", ln=True, align='C')
    pdf.ln(5)
    
    # Datos del Cliente
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 8, txt=f"Titular: {cliente_info[0]}", ln=True)
    pdf.cell(200, 8, txt=f"Nro. Cuenta: {cliente_info[1]}", ln=True)
    pdf.cell(200, 8, txt=f"Saldo Disponible: ${cliente_info[2]:.2f}", ln=True)
    pdf.ln(10)
    
    # Cabecera de la Tabla
    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(27, 138, 71) # Verde claro (#1b8a47)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(60, 10, "Fecha", border=1, fill=True, align='C')
    pdf.cell(70, 10, "Tipo de Movimiento", border=1, fill=True, align='C')
    pdf.cell(60, 10, "Monto", border=1, fill=True, align='C')
    pdf.ln()
    
    # Filas de la Tabla
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

    # Retornar el PDF directamente en memoria sin guardarlo en disco
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
        # CORRECCIÓN AQUÍ: Convertimos el Decimal de PostgreSQL a float de Python
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
        # IMPRIMIR EL ERROR EN LA TERMINAL PARA NO ESTAR CIEGOS
        print(f"CRITICAL ERROR EN RETIRO: {e}") 
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
        # Bloqueo transaccional
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
        
        # Operación matemática de suma
        nuevo_saldo = saldo_actual + monto_deposito
        
        # Actualización e inserción en el historial
        cur.execute("UPDATE cuentas SET saldo = %s WHERE id = %s", (nuevo_saldo, cuenta_id))
        cur.execute("INSERT INTO transacciones (cuenta_id, tipo, monto) VALUES (%s, 'Deposito', %s)", (cuenta_id, monto_deposito))
        
        conn.commit()
        return jsonify({'success': True, 'message': f'Depósito exitoso de ${monto_deposito:.2f}.'})
        
    except Exception as e:
        conn.rollback()
        print(f"CRITICAL ERROR EN DEPOSITO: {e}") 
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
    servicio = data.get('servicio') # Ej: "Luz", "Agua", "Internet"
    
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
        
        # Generar nombre del movimiento, limitando a 20 caracteres por el esquema de BD
        tipo_movimiento = f"Pago {servicio}"[:20] 
        
        cur.execute("UPDATE cuentas SET saldo = %s WHERE id = %s", (nuevo_saldo, cuenta_id))
        cur.execute("INSERT INTO transacciones (cuenta_id, tipo, monto) VALUES (%s, %s, %s)", (cuenta_id, tipo_movimiento, monto_pago))
        
        conn.commit()
        return jsonify({'success': True, 'message': f'Pago de {servicio} por ${monto_pago:.2f} procesado exitosamente.'})
        
    except Exception as e:
        conn.rollback()
        print(f"CRITICAL ERROR EN PAGO DE SERVICIO: {e}") 
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

    # Obtener los datos actuales del cliente para el recibo
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

    # --- CREACIÓN DEL COMPROBANTE PDF ---
    pdf = FPDF()
    pdf.add_page()
    
    # Cabecera
    pdf.set_font("Arial", 'B', 18)
    pdf.set_text_color(25, 79, 43) # Verde CajeBank
    pdf.cell(200, 10, txt="CajeBank", ln=True, align='C')
    
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(200, 10, txt="Comprobante de Pago de Servicio", ln=True, align='C')
    pdf.ln(10)
    
    # Datos de la Transacción
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 8, txt=f"Fecha y Hora: {fecha_actual}", ln=True)
    pdf.cell(200, 8, txt=f"Titular de la Cuenta: {cliente_info[0]}", ln=True)
    pdf.cell(200, 8, txt=f"Nro. de Cuenta: {cliente_info[1]}", ln=True)
    pdf.ln(5)
    
    # Detalles del Cobro
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 8, txt=f"Servicio Pagado: {servicio}", ln=True)
    pdf.set_text_color(200, 0, 0) # Rojo para el débito
    pdf.cell(200, 8, txt=f"Monto Debitado: ${float(monto):.2f}", ln=True)
    
    # Saldo Restante
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 8, txt=f"Saldo Disponible: ${cliente_info[2]:.2f}", ln=True)
    
    # Pie de página
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(200, 10, txt="Gracias por confiar en CajeBank. Tu cajero, tu aliado.", ln=True, align='C')

    # Retornar el PDF en memoria
    pdf_output = pdf.output(dest='S').encode('latin1')
    return send_file(io.BytesIO(pdf_output), mimetype='application/pdf', as_attachment=True, download_name=f'Comprobante_{servicio}.pdf')

if __name__ == '__main__':
    app.run(debug=True, port=5000)