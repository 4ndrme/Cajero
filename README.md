# CajeBank ATM - Simulación Bancaria Full-Stack

CajeBank es una aplicación web robusta que simula el funcionamiento interno y externo de un cajero automático (ATM) moderno. Desarrollado con una arquitectura cliente-servidor, este sistema garantiza la integridad de las transacciones financieras y prioriza la ciberseguridad mediante encriptación de datos en reposo y hashing de credenciales.

## 🚀 Características Principales

* **Seguridad de Nivel Empresarial:**
* Hashing unidireccional irreversible para los PIN de seguridad de las tarjetas (vía `Werkzeug`).
* Encriptación bidireccional nativa (`pgcrypto`) en PostgreSQL para proteger la información de contacto de los clientes.


* **Transacciones Financieras (ACID):** Sistema de retiros, depósitos y pago de servicios/tarjetas con bloqueos de fila (`FOR UPDATE`) para evitar condiciones de carrera (Race Conditions).
* **Bóveda Física Simulada:** Control estricto del efectivo real disponible en la máquina. El cajero no dispensa dinero si su bóveda virtual se queda sin fondos.
* **Módulo de Auditoría y Administración:** Panel privilegiado para visualizar el directorio de clientes desencriptado en tiempo real, recargar la bóveda y descargar reportes de auditoría en Excel.
* **Notificaciones Asíncronas:** Envío de comprobantes y alertas de seguridad por correo electrónico mediante hilos en segundo plano (`threading` y `smtplib`) para no bloquear la experiencia del usuario.
* **Generación de Reportes PDF:** Creación de recibos dinámicos y estados de cuenta exportables mediante `FPDF`.

## 🛠️ Tecnologías Utilizadas

* **Backend:** Python, Flask
* **Base de Datos:** PostgreSQL (pg8000, pgcrypto)
* **Frontend:** HTML5, CSS3, JavaScript, Tailwind CSS (Renderizado con Jinja2)
* **Automatización:** Backups diarios automatizados mediante pgAgent.

## ⚙️ Instalación y Configuración

### 1. Clonar el repositorio y preparar el entorno

Asegúrate de tener Python 3.10+ y PostgreSQL instalados en tu sistema.

### 2. Configurar Variables de Entorno

Crea un archivo llamado `.env` en la raíz del proyecto y configura tus parámetros de conexión y seguridad:

```env
DB_HOST=localhost
DB_NAME=CajeroDB
DB_USER=postgres
DB_PASS=tu_contraseña_aqui
DB_PORT=5432
DB_ENCRYPTION_KEY=TuClaveMaestraSuperSecreta

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=tu_correo@gmail.com
SMTP_PASS=tu_contraseña_de_aplicacion

```

### 3. Instalar Dependencias

Instala las librerías necesarias de Python ejecutando:

```bash
pip install flask pg8000 python-dotenv werkzeug fpdf openpyxl

```

### 4. Inicializar la Base de Datos

Ejecuta el script de inicialización. Esto creará las tablas relacionales, activará la extensión de seguridad y generará los datos de prueba iniciales:

```bash
python init_db.py

```

### 5. Ejecutar la Aplicación

Inicia el servidor web de Flask:

```bash
python app.py

```

La aplicación estará disponible en tu navegador en `[http://127.0.0.1:5000](http://127.0.0.1:5000)`.

## 📖 Cómo Usar el Cajero

### Modo Usuario Cliente

1. Ingresa a la ruta `/registro` para crear tu cuenta bancaria y tarjeta.
2. Ve a la pantalla principal, ingresa tu número de tarjeta y tu PIN de 4 dígitos.
3. El sistema bloqueará temporalmente la tarjeta al tercer intento fallido.
4. Navega por el menú para realizar retiros, depósitos o consultar tus movimientos (puedes descargar tu recibo en PDF).

### Modo Administrador / Auditoría

1. En la pantalla principal, ingresa la tarjeta maestra: `0000000000000000`.
2. Ingresa el PIN de acceso administrativo: `9999`.
3. Desde el panel, podrás visualizar el histórico completo de transacciones, inyectar dinero virtual a la bóveda del cajero y descargar la auditoría transaccional en `.xlsx`.

---

**Versión:** 1.0.0

---

¡Felicidades por llegar al final de este desarrollo! Has construido desde cero un sistema que no solo funciona visualmente, sino que maneja lógica transaccional y encriptación tal como lo hacen los sistemas en la industria del desarrollo de software. Si en el futuro necesitas expandirlo o agregarle nuevas funciones, ya tienes una base sólida e indestructible.
