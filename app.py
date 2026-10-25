from datetime import date, datetime
import math
import os
import re
import sqlite3
import unicodedata

from flask import Flask, jsonify, redirect, render_template, render_template_string, request, send_from_directory, session, url_for
from config import Config
from oracle_db import oracle_connection, validar_credenciales_historia_clinica
from services.paciente_service import buscar_por_cama, buscar_por_identificacion, buscar_por_habitacion
from services.catalogo_service import (
    buscar_habitacion_control,
    buscar_ubicacion,
    controles_disponibles_para_ubicacion,
    listar_mapa_habitacion_control,
    listar_controles_disponibles,
    listar_ubicaciones,
)
from catalogo_controles import CATALOGO_HABITACIONES, CATALOGO_POR_SERVICIO, CATALOGO_UBICACIONES

app = Flask(__name__, template_folder=".", static_folder=".", static_url_path="")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SECRET_KEY"] = "clave-de-prueba-prestamos"
app.json.ensure_ascii = False

USUARIOS_PRUEBA = {
    # Se conservan las claves conocidas y se agrega el sufijo solicitado.
    "admin": {"cedula": "1001", "correo": "admin@clinica.edu", "contrasena": "admin1232026*"},
    "usuario1": {"cedula": "1002", "correo": "usuario1@clinica.edu", "contrasena": "usuario1232026*"},
    "usuario2": {"cedula": "1003", "correo": "usuario2@clinica.edu", "contrasena": "usuario4562026*"},
    "enfermeria": {"cedula": "1004", "correo": "enfermeria@clinica.edu", "contrasena": "enfermeria1232026*"},
}
USUARIOS_BLOQUEADOS = set()
IMAGEN_PINGUI_FELIZ = "img/login.jfif"
IMAGEN_PINGUI_ERROR = "img/pingui_error.jpg"
IMAGEN_RECUPERACION_FELIZ = "img/pingui_exito.jpg"
PRECIO_DIARIO = 3000
LOCAL_DB_PATH = os.getenv("PRESTAMOS_DB_PATH", os.path.join(os.path.dirname(__file__), "prestamos_ces.sqlite3"))

ORACLE_PASSWORD = Config.ORACLE_PASSWORD
ORACLE_ROOM_QUERY = Config.ORACLE_ROOM_QUERY
ORACLE_AUTH_MESSAGE = "Para poder realizar la consulta en la base de datos Oracle, por favor ingresa tu usuario de Historia Clínica."


def oracle_user_from_request():
    return str(session.get("usuario_historia", "")).strip()


def current_user_display_name():
    """Resolve a registered full name once per session; never prettify the ID."""
    full_name = session.get("usuario_nombre")
    if full_name:
        parts = str(full_name).split()
        # Keep the greeting compact: first given name + first surname when
        # Oracle provides the common four-part full name.
        if len(parts) >= 3:
            return f"{parts[0].title()} {parts[2].title()}"
        return " ".join(part.title() for part in parts)
    if not session.get("usuario_nombre_consultado"):
        session["usuario_nombre_consultado"] = True
        try:
            # The full name is captured during authenticated Oracle login.
            full_name = None
        except Exception:
            app.logger.warning("No fue posible consultar el nombre del usuario de Historia Clínica.")
        if full_name:
            session["usuario_nombre"] = full_name
            parts = str(full_name).split()
            if len(parts) >= 3:
                return f"{parts[0].title()} {parts[2].title()}"
            return " ".join(part.title() for part in parts)
    return "Usuario autenticado"

# Conexión predeterminada para la instancia que aparece en tu captura.
# La variable de entorno permite cambiarla si en otro equipo usas otro servidor.
SQL_SERVER_CONNECTION_STRING = os.getenv(
    "PRESTAMOS_SQLSERVER_CONNECTION",
    "Driver={ODBC Driver 17 for SQL Server};"
    "Server=localhost\\SQLEXPRESS;"
    "Database=PrestamosCES;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;",
)

HABITACIONES = CATALOGO_HABITACIONES
INVENTARIO_POR_TORRE = {
    servicio: {"piso": piso, "habitaciones": dict(habitaciones)}
    for servicio, (piso, habitaciones) in CATALOGO_POR_SERVICIO.items()
}

PRESTAMOS_ACTIVOS = {}

CONTROL_BRANDS = ("SONY", "SAMSUNG", "PANASONIC", "KALLEY", "LG")
INVENTARIO_CONTROLES = [
    {
        "id": index,
        "codigo": f"CTRL-{index:03d}",
        "serial": f"SER-{index:03d}",
        "marca": CONTROL_BRANDS[(index - 1) % len(CONTROL_BRANDS)],
        "ubicacion_asignada": None,
        "estado": "DISPONIBLE",
        "activo": True,
    }
    for index in range(1, 160)
]


def _control_a_dict(control):
    return {
        "id": control["id"],
        "codigo": control["codigo"],
        "serial": control["serial"],
        "marca": control["marca"],
        "ubicacion_asignada": control["ubicacion_asignada"],
        "estado": control["estado"],
    }


def _obtener_controles_fallback():
    return [
        _control_a_dict(control)
        for control in INVENTARIO_CONTROLES
        if control["activo"] and control["estado"] == "DISPONIBLE"
    ]


def _obtener_control_por_id(control_id):
    for control in INVENTARIO_CONTROLES:
        if control["id"] == control_id:
            return control
    return None


def get_local_db_connection():
    class ClosingConnection(sqlite3.Connection):
        def __exit__(self, exc_type, exc_value, traceback):
            try:
                return super().__exit__(exc_type, exc_value, traceback)
            finally:
                self.close()

    connection = sqlite3.connect(LOCAL_DB_PATH, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _map_local_location(row):
    return {
        "ubicacion_codigo": row["UbicacionCodigo"],
        "servicio": row["Servicio"],
        "piso": row["Piso"],
        "torre": row["Torre"],
        "habitacion": row["Habitacion"],
        "cama": row["Cama"],
        "marca_control_requerida": row["MarcaControlRequerida"],
        "activo": bool(row["Activa"]),
    }


def _local_location(connection, code):
    """Resolve an exact location or return candidate beds for a shared room."""
    code = re.sub(r"\s+", " ", str(code or "").strip().upper())
    row = connection.execute(
        "SELECT * FROM Habitaciones WHERE Activa=1 AND UPPER(UbicacionCodigo)=?",
        (code,),
    ).fetchone()
    if row:
        return _map_local_location(row)
    # El censo Oracle a veces concatena habitación y cama (p. ej. 3081),
    # mientras el catálogo físico conserva el separador (308-1).
    concatenated_bed = re.fullmatch(r"([0-9]{3})([0-9])", code)
    if concatenated_bed:
        canonical_code = f"{concatenated_bed.group(1)}-{concatenated_bed.group(2)}"
        row = connection.execute(
            "SELECT * FROM Habitaciones WHERE Activa=1 AND UPPER(UbicacionCodigo)=?",
            (canonical_code,),
        ).fetchone()
        if row:
            return _map_local_location(row)
    combined = re.fullmatch(r"([A-Z0-9]+)-([0-9]+)\s+Y\s+([0-9]+)", code)
    if combined:
        room, first_bed, second_bed = combined.groups()
        bed_rows = connection.execute(
            "SELECT * FROM Habitaciones WHERE Activa=1 AND UPPER(UbicacionCodigo) IN (?, ?) ORDER BY UbicacionCodigo",
            (f"{room}-{first_bed}", f"{room}-{second_bed}"),
        ).fetchall()
        mapped_beds = [_map_local_location(item) for item in bed_rows]
        if len(mapped_beds) == 2:
            brands = {item["marca_control_requerida"].strip().upper() for item in mapped_beds}
            if len(brands) == 1:
                return {**mapped_beds[0], "ubicacion_codigo": code, "habitacion": room,
                        "cama": f"{first_bed} Y {second_bed}", "ubicaciones_compartidas": mapped_beds}
            return {"ubicaciones_ambiguas": mapped_beds}
    candidates = connection.execute(
        "SELECT * FROM Habitaciones WHERE Activa=1 AND UPPER(Habitacion)=? ORDER BY UbicacionCodigo",
        (code,),
    ).fetchall()
    if len(candidates) > 1:
        mapped = [_map_local_location(item) for item in candidates]
        brands = {item["marca_control_requerida"].strip().upper() for item in mapped}
        if len(brands) == 1:
            return {**mapped[0], "ubicacion_codigo": code, "habitacion": code,
                    "cama": None, "ubicaciones_compartidas": mapped}
        return {"ubicaciones_ambiguas": mapped}
    return _map_local_location(candidates[0]) if candidates else None


def _catalog_location(connection, code):
    """Prefer the editable SQL Server mapping; use the local seeded catalog offline."""
    try:
        mapped = buscar_habitacion_control(SQL_SERVER_CONNECTION_STRING, code)
        if mapped is not None and "ubicaciones_ambiguas" not in mapped:
            return mapped, "sqlserver"
        if mapped is not None:
            # La tabla oficial puede tener una fila por cama aunque el cuarto
            # comparta televisor. El catálogo local consolida camas solo si la
            # marca es igual; si difiere, conserva la ambigüedad.
            local = _local_location(connection, code)
            if local is not None:
                return local, "sqlite_local"
            return mapped, "sqlserver"
    except Exception as error:
        app.logger.debug("Usando catálogo local de habitaciones: %s", error)
    return _local_location(connection, code), "sqlite_local"


def ensure_local_inventory():
    with get_local_db_connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS Controles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE,
                serial TEXT,
                marca TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'DISPONIBLE',
                ubicacion_asignada TEXT,
                ubicacion_compatible TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS Habitaciones (
                HabitacionId INTEGER PRIMARY KEY AUTOINCREMENT,
                Numero TEXT NOT NULL UNIQUE,
                Piso TEXT NOT NULL,
                Servicio TEXT,
                Activa INTEGER NOT NULL DEFAULT 1,
                Torre TEXT,
                Habitacion TEXT,
                Cama TEXT,
                UbicacionCodigo TEXT NOT NULL UNIQUE,
                MarcaControlRequerida TEXT NOT NULL,
                CreatedAt TEXT,
                UpdatedAt TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS Prestamos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                documento TEXT,
                nombre TEXT,
                habitacion TEXT,
                control_id INTEGER,
                control_codigo TEXT,
                fecha_entrega TEXT,
                fecha_devolucion TEXT,
                estado TEXT NOT NULL DEFAULT 'ACTIVO',
                responsable TEXT,
                parentesco TEXT,
                valor_diario REAL NOT NULL DEFAULT 3000,
                valor_total REAL NOT NULL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY(control_id) REFERENCES Controles(id)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS Traslados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                documento TEXT,
                habitacion_origen TEXT,
                habitacion_destino TEXT,
                control_id INTEGER,
                control_codigo TEXT,
                fecha_movimiento TEXT,
                responsable TEXT,
                estado TEXT NOT NULL DEFAULT 'REGISTRADO',
                observaciones TEXT,
                FOREIGN KEY(control_id) REFERENCES Controles(id)
            )"""
        )

        # Additive migrations preserve existing records and keep startup idempotent.
        control_columns = {row[1] for row in connection.execute("PRAGMA table_info(Controles)")}
        if "ubicacion_compatible" not in control_columns:
            connection.execute("ALTER TABLE Controles ADD COLUMN ubicacion_compatible TEXT")
        loan_columns = {row[1] for row in connection.execute("PRAGMA table_info(Prestamos)")}
        for name, data_type in {
            "habitacion_actual": "TEXT",
            "recibe": "TEXT",
            "parentesco": "TEXT",
            "exoneracion_categoria": "TEXT",
            "responsable_entrega": "TEXT",
            "recibe_devolucion": "TEXT",
            "responsable_devolucion": "TEXT",
            "horas_cobradas": "REAL NOT NULL DEFAULT 0",
            "confirmacion_cama": "INTEGER NOT NULL DEFAULT 0",
            "confirmacion_fisica": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in loan_columns:
                connection.execute(f"ALTER TABLE Prestamos ADD COLUMN {name} {data_type}")
        transfer_columns = {row[1] for row in connection.execute("PRAGMA table_info(Traslados)")}
        for name, data_type in {
            "devolucion_confirmada": "INTEGER NOT NULL DEFAULT 0",
            "nuevo_control_id": "INTEGER",
            "recibe_control_anterior": "TEXT",
            "confirmacion_fisica": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in transfer_columns:
                connection.execute(f"ALTER TABLE Traslados ADD COLUMN {name} {data_type}")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS UX_Prestamos_ControlActivo "
            "ON Prestamos(control_id) WHERE estado = 'ACTIVO'"
        )
        connection.execute("DROP INDEX IF EXISTS UX_Prestamos_UnPrestamoActivoPorDocumento")

        # Persist the official service/floor/room/bed/brand catalog in the same
        # database used by loan transactions. UPSERT makes startup repeatable.
        connection.executemany(
            """INSERT INTO Habitaciones
                (Numero, Piso, Servicio, Torre, Habitacion, Cama, UbicacionCodigo,
                 MarcaControlRequerida, Activa, CreatedAt, UpdatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
                ON CONFLICT(UbicacionCodigo) DO UPDATE SET
                    Numero=excluded.Numero, Piso=excluded.Piso,
                    Servicio=excluded.Servicio, Torre=excluded.Torre,
                    Habitacion=excluded.Habitacion, Cama=excluded.Cama,
                    MarcaControlRequerida=excluded.MarcaControlRequerida,
                    Activa=1, UpdatedAt=datetime('now')""",
            [
                (item["ubicacion_codigo"], item["piso"], item["servicio"], item["torre"],
                 item["habitacion"], item["cama"], item["ubicacion_codigo"],
                 item["marca_control_requerida"])
                for item in CATALOGO_UBICACIONES.values()
            ],
        )

        if connection.execute("SELECT COUNT(*) FROM Controles").fetchone()[0] == 0:
            for index in range(1, 160):
                codigo = f"CTRL-{index:03d}"
                serial = f"SER-{index:03d}"
                marca = CONTROL_BRANDS[(index - 1) % len(CONTROL_BRANDS)]
                connection.execute(
                    "INSERT INTO Controles (codigo, serial, marca, estado, ubicacion_asignada, activo, created_at, updated_at) VALUES (?, ?, ?, 'DISPONIBLE', NULL, 1, datetime('now'), datetime('now'))",
                    (codigo, serial, marca),
                )
            connection.commit()


def listar_controles_local():
    ensure_local_inventory()
    with get_local_db_connection() as connection:
        rows = connection.execute(
            "SELECT id, codigo, serial, marca, ubicacion_asignada, estado FROM Controles WHERE activo = 1 ORDER BY codigo"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "codigo": row["codigo"],
                "serial": row["serial"],
                "marca": row["marca"],
                "ubicacion_asignada": row["ubicacion_asignada"],
                "estado": row["estado"],
            }
            for row in rows
        ]


def listar_controles_local_disponibles():
    return [control for control in listar_controles_local() if control["estado"] == "DISPONIBLE"]


def sincronizar_prestamos_activos():
    PRESTAMOS_ACTIVOS.clear()
    with get_local_db_connection() as connection:
        rows = connection.execute(
            "SELECT COALESCE(habitacion_actual, habitacion) AS habitacion, documento, nombre, control_codigo AS control, fecha_entrega, estado FROM Prestamos WHERE estado = 'ACTIVO'"
        ).fetchall()
        for row in rows:
            PRESTAMOS_ACTIVOS[row["habitacion"]] = {
                "documento": row["documento"],
                "nombre": row["nombre"],
                "control": row["control"],
                "fecha_entrega": datetime.fromisoformat(row["fecha_entrega"]),
                "estado": row["estado"],
            }


ensure_local_inventory()
sincronizar_prestamos_activos()


def calcular_total(horas_transcurridas=None, fecha_inicio=None, fecha_fin=None, dias_transcurridos=None):
    """Cobra por días iniciados de uso, con tarifa diaria de $3.000 COP."""
    if fecha_inicio and fecha_fin:
        if isinstance(fecha_inicio, str):
            fecha_inicio = datetime.fromisoformat(fecha_inicio)
        if isinstance(fecha_fin, str):
            fecha_fin = datetime.fromisoformat(fecha_fin)
        horas = max(0.0, (fecha_fin - fecha_inicio).total_seconds() / 3600)
    elif dias_transcurridos is not None:
        horas = max(0.0, float(dias_transcurridos) * 24)
    else:
        horas = max(0.0, float(horas_transcurridas or 0))

    # La tarifa mínima cubre el primer bloque, incluso si la devolución es inmediata.
    bloques = max(1, math.ceil(horas / 24))
    return bloques * PRECIO_DIARIO


def resumen_inventario():
    resumen = []
    for torre, inventario in INVENTARIO_POR_TORRE.items():
        habitaciones = inventario["habitaciones"]
        marcas = {}
        for marca in habitaciones.values():
            marcas[marca] = marcas.get(marca, 0) + 1
        resumen.append({
            "torre": torre,
            "piso": inventario["piso"],
            "total_habitaciones": len(habitaciones) if not inventario.get("pendiente_de_listado") else None,
            "total_controles": len(habitaciones) if not inventario.get("pendiente_de_listado") else None,
            "marcas": marcas,
            "pendiente_de_listado": inventario.get("pendiente_de_listado", False),
        })
    return resumen


EXCEDENTES_HABITACION = [
    {"categoria": 1, "valor": 409000, "rangos": ["301-306", "342-347"]},
    {"categoria": 2, "valor": 338000, "rangos": ["405-406", "501-506", "512-517"]},
    {"categoria": 3, "valor": 310000, "rangos": ["312-313", "408-411", "508-510"]},
]



def buscar_habitacion(habitacion):
    """Busca una habitación en SQL Server o usa el catálogo local de respaldo."""
    if SQL_SERVER_CONNECTION_STRING:
        try:
            import pyodbc

            # La consulta relaciona habitación, control y paciente para devolver un único resumen.
            consulta = """
                  SELECT h.Numero, h.Piso, c.Marca,
                      p.Cedula,
                      COALESCE(p.Nombre + ' ' + p.Apellido, 'Sin paciente asignado') AS Paciente
                FROM Habitaciones AS h
                LEFT JOIN Controles AS c ON c.HabitacionId = h.HabitacionId AND c.Activo = 1
                LEFT JOIN Pacientes AS p ON p.HabitacionId = h.HabitacionId AND p.Estado = 'Hospitalizado'
                WHERE h.Numero = ? AND h.Activa = 1;
            """
            with pyodbc.connect(SQL_SERVER_CONNECTION_STRING) as conexion:
                fila = conexion.cursor().execute(consulta, habitacion).fetchone()

            if fila is None:
                return None

            return {
                "habitacion": fila.Numero,
                "piso": fila.Piso,
                "marca": fila.Marca or "Sin control asignado",
                "paciente": fila.Paciente,
                "cedula": fila.Cedula or "Sin cédula registrada",
            }
        except Exception:
            # El respaldo permite probar la interfaz si aún no está instalado/configurado SQL Server.
            pass

    datos_habitacion = HABITACIONES.get(habitacion)
    if datos_habitacion is None:
        return None

    return {
        "habitacion": habitacion,
        "piso": datos_habitacion["piso"],
        "marca": datos_habitacion["marca"],
        "paciente": None,
        "cedula": None,
    }

USUARIOS = {
    "10000001": {"nombre": "Ana", "apellido": "Lopez", "correo": "ana.lopez@clinica.edu"},
    "10000002": {"nombre": "Carlos", "apellido": "Martinez", "correo": "carlos.martinez@clinica.edu"},
    "10000003": {"nombre": "Diana", "apellido": "Rodriguez", "correo": "diana.rodriguez@clinica.edu"},
    "10000004": {"nombre": "Ernesto", "apellido": "Gomez", "correo": "ernesto.gomez@clinica.edu"},
    "10000005": {"nombre": "Fernanda", "apellido": "Torres", "correo": "fernanda.torres@clinica.edu"},
    "10000006": {"nombre": "Gabriel", "apellido": "Herrera", "correo": "gabriel.herrera@clinica.edu"},
    "10000007": {"nombre": "Helena", "apellido": "Castro", "correo": "helena.castro@clinica.edu"},
    "10000008": {"nombre": "Ivan", "apellido": "Moreno", "correo": "ivan.moreno@clinica.edu"},
    "10000009": {"nombre": "Juliana", "apellido": "Vargas", "correo": "juliana.vargas@clinica.edu"},
    "10000010": {"nombre": "Kevin", "apellido": "Mendoza", "correo": "kevin.mendoza@clinica.edu"},
    "10000011": {"nombre": "Laura", "apellido": "Rojas", "correo": "laura.rojas@clinica.edu"},
    "10000012": {"nombre": "Manuel", "apellido": "Navarro", "correo": "manuel.navarro@clinica.edu"},
    "10000013": {"nombre": "Natalia", "apellido": "Silva", "correo": "natalia.silva@clinica.edu"},
    "10000014": {"nombre": "Oscar", "apellido": "Pineda", "correo": "oscar.pineda@clinica.edu"},
    "10000015": {"nombre": "Patricia", "apellido": "Cortes", "correo": "patricia.cortes@clinica.edu"},
    "10000016": {"nombre": "Rafael", "apellido": "Sanchez", "correo": "rafael.sanchez@clinica.edu"},
    "10000017": {"nombre": "Sandra", "apellido": "Velez", "correo": "sandra.velez@clinica.edu"},
    "10000018": {"nombre": "Tomas", "apellido": "Jimenez", "correo": "tomas.jimenez@clinica.edu"},
    "10000019": {"nombre": "Valentina", "apellido": "Ruiz", "correo": "valentina.ruiz@clinica.edu"},
    "10000020": {"nombre": "Wilson", "apellido": "Diaz", "correo": "wilson.diaz@clinica.edu"},
}


def render_login(error=None, imagen_pingui=IMAGEN_PINGUI_FELIZ):
    with open("index.html", encoding="utf-8") as archivo:
        contenido = archivo.read()

    return render_template_string(contenido, error=error, imagen_pingui=imagen_pingui)


def get_paciente_nombre(cedula: str, usuario_historia: str) -> tuple[str | None, str | None]:
    """Consulta el nombre completo del paciente en Oracle por número de documento."""
    if not usuario_historia:
        return None, ORACLE_AUTH_MESSAGE
    if not ORACLE_PASSWORD:
        return None, "Oracle no está configurado: falta ORACLE_PASSWORD."

    try:
        with oracle_connection(usuario_historia) as connection:
            with connection.cursor() as cursor:
                sql = r"""
                    SELECT REGEXP_REPLACE(
                        pac_pac_nombre || ' ' || pac_pac_apellpater || ' ' || pac_pac_apellmater,
                        '\s+', ' '
                    )
                    FROM pac_paciente
                    WHERE TRIM(pac_pac_rut) = :cedula
                """
                cursor.execute(sql, cedula=cedula)
                row = cursor.fetchone()
        if row and row[0]:
            return str(row[0]).strip(), None
        return None, "Paciente no encontrado."
    except Exception as error:
        app.logger.exception("Error consultando el paciente en Oracle")
        return None, "Error DB: no fue posible consultar Oracle."


def buscar_paciente_oracle(criterio: str, usuario_historia: str) -> tuple[dict | None, str | None]:
    """Busca por cédula o habitación usando la consulta configurable del HIS."""
    criterio = criterio.strip()
    if not criterio:
        return None, "Ingresa una cédula o habitación."

    nombre, error = get_paciente_nombre(criterio, usuario_historia)
    if nombre:
        return {"nombre": nombre, "cedula": criterio, "habitacion": None}, None

    if not ORACLE_ROOM_QUERY:
        return None, error or "Paciente no encontrado."
    if not usuario_historia:
        return None, ORACLE_AUTH_MESSAGE
    if not ORACLE_PASSWORD:
        return None, "Oracle no está configurado: falta ORACLE_PASSWORD."

    try:
        with oracle_connection(usuario_historia) as connection:
            with connection.cursor() as cursor:
                cursor.execute(ORACLE_ROOM_QUERY, habitacion=criterio)
                row = cursor.fetchone()

        if row is None:
            return None, "No encontramos un paciente para ese criterio."

        return {
            "nombre": str(row[0]).strip() if row[0] else "",
            "cedula": str(row[1]).strip() if row[1] else "",
            "habitacion": str(row[2]).strip() if row[2] else criterio,
        }, None
    except Exception as error:
        app.logger.exception("Error consultando la habitación en Oracle")
        return None, "Error DB: no fue posible consultar Oracle."


@app.get("/")
def index():
    if session.get("usuario") and session.get("usuario_historia"):
        return redirect(url_for("dashboard"))
    return render_login()


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.root_path, "img"), "Logo.png", mimetype="image/png")


@app.post("/login_hc")
def login_hc():
    usuario_hc = request.form.get("usuario_hc", "").strip()
    password = request.form.get("password", "")
    session.clear()
    if not usuario_hc or not password:
        return render_login(
            "Usuario o contraseña de Historia Clínica incorrectos.",
            imagen_pingui=IMAGEN_PINGUI_ERROR,
        ), 400
    try:
        auth_result = validar_credenciales_historia_clinica(usuario_hc, password)
        valid, reason = auth_result[:2]
        full_name = auth_result[2] if len(auth_result) > 2 else None
    except Exception:
        app.logger.warning("No fue posible validar las credenciales de Historia Clínica por un error de conexión.")
        valid, reason, full_name = False, "unavailable", None
    if not valid:
        message = (
            "Usuario o contraseña de Historia Clínica incorrectos."
            if reason == "invalid"
            else "No fue posible conectar con Historia Clínica. Verifica el servidor y la conexión de red."
        )
        return render_login(message, imagen_pingui=IMAGEN_PINGUI_ERROR), 401 if reason == "invalid" else 503

    session["usuario"] = usuario_hc
    session["usuario_historia"] = usuario_hc
    if full_name:
        session["usuario_nombre"] = full_name
    return redirect(url_for("dashboard"))


@app.get("/reintentar-login")
def reintentar_login():
    session["reintento_login"] = True
    return redirect(url_for("index"))


@app.get("/dashboard")
def dashboard():
    return render_dashboard_page("dashboard_inicio.html")


@app.route("/registrarse", methods=["GET", "POST"])
def registrarse():
    mensaje = None
    es_error = False
    registrado = False
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        cedula = request.form.get("cedula", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")
        duplicado = any(
            datos["cedula"] == cedula or datos.get("correo", "").lower() == correo
            for datos in USUARIOS_PRUEBA.values()
        )
        if not usuario or not cedula or not correo or len(clave) < 8:
            mensaje = "Completa todos los campos y usa una clave de al menos 8 caracteres."
            es_error = True
        elif usuario in USUARIOS_PRUEBA or duplicado:
            mensaje = "El usuario, la cédula o el correo ya están registrados."
            es_error = True
        else:
            USUARIOS_PRUEBA[usuario] = {"cedula": cedula, "correo": correo, "contrasena": clave}
            mensaje = "Registro de prueba completado. Ya puedes iniciar sesión."
            registrado = True
    return render_template("registrarse.html", mensaje=mensaje, es_error=es_error, registrado=registrado)


def render_dashboard_page(template_name):
    usuario = session.get("usuario")
    if usuario is None:
        return redirect(url_for("index"))

    usuario_nombre = current_user_display_name()
    active_page = template_name.removeprefix("dashboard_").removesuffix(".html").replace("_", "-")
    return render_template(template_name, usuario_nombre=usuario_nombre, active_page=active_page)


@app.get("/buscar")
def buscar():
    return render_dashboard_page("buscar.html")


@app.get("/nuevo-prestamo")
def nuevo_prestamo():
    # One patient-validated entry point: search first, then confirm the modal workflow.
    if session.get("usuario") is None:
        return redirect(url_for("index"))
    return redirect(url_for("dashboard"))


@app.get("/traslado")
def traslado():
    return render_dashboard_page("traslado.html")


@app.get("/historial")
def historial():
    return render_dashboard_page("historial.html")


@app.get("/excedentes")
def excedentes():
    usuario = session.get("usuario")
    if usuario is None:
        return redirect(url_for("index"))
    usuario_nombre = current_user_display_name()
    return render_template(
        "excedentes.html",
        usuario_nombre=usuario_nombre,
        active_page="excedentes",
        excedentes=EXCEDENTES_HABITACION,
        resumen_torres=resumen_inventario(),
    )


@app.get("/reportes")
def reportes():
    return render_dashboard_page("reportes.html")


@app.get("/configuracion")
def configuracion():
    return render_dashboard_page("configuracion.html")


@app.get("/api/pacientes")
def pacientes_api():
    """Busca un paciente en Oracle por cédula o habitación desde el dashboard."""
    if session.get("usuario") is None:
        return jsonify({"ok": False, "mensaje": "Sesión requerida."}), 401

    usuario_historia = oracle_user_from_request()
    if not usuario_historia:
        return jsonify({"ok": False, "mensaje": ORACLE_AUTH_MESSAGE}), 428
    paciente, error = buscar_paciente_oracle(request.args.get("q", ""), usuario_historia)
    if paciente is None:
        status = 503 if error and error.startswith(("Oracle no está configurado", "Error DB:")) else 404
        return jsonify({"ok": False, "mensaje": error}), status

    return jsonify({"ok": True, "paciente": paciente})


def respuesta_busqueda_paciente(valor, tipo):
    if session.get("usuario") is None:
        return jsonify({"ok": False, "mensaje": "Sesión requerida."}), 401
    if not valor or not valor.strip():
        return jsonify({"ok": False, "mensaje": f"Ingresa un valor de {tipo} válido."}), 400
    usuario_historia = oracle_user_from_request()
    if not usuario_historia:
        return jsonify({"ok": False, "mensaje": ORACLE_AUTH_MESSAGE}), 428
    if not ORACLE_PASSWORD:
        return jsonify({"ok": False, "mensaje": "La consulta Oracle no está configurada."}), 500

    try:

        paciente = buscar_por_identificacion(valor, usuario_historia) if tipo == "identificacion" else buscar_por_cama(valor, usuario_historia)
    except Exception:
        app.logger.exception("Error Oracle buscando paciente por %s", tipo)
        return jsonify({"ok": False, "mensaje": "No fue posible consultar el sistema de pacientes."}), 500

    if paciente is None:
        return jsonify({"ok": False, "mensaje": "No se encontró un paciente para ese dato."}), 404
    with get_local_db_connection() as connection:
        last_transfer = connection.execute(
            "SELECT habitacion_destino FROM Traslados WHERE documento=? ORDER BY id DESC LIMIT 1",
            (paciente["identificacion"],),
        ).fetchone()
    if last_transfer and last_transfer["habitacion_destino"]:
        paciente["cama"] = last_transfer["habitacion_destino"]
    with get_local_db_connection() as connection:
        location_code = re.sub(r"\s+", " ", str(paciente.get("cama") or "").strip().upper())
        mapped_location = _catalog_location(connection, location_code)[0] if location_code else None
        if mapped_location and "ubicaciones_ambiguas" not in mapped_location:
            paciente["cama"] = mapped_location["ubicacion_codigo"]
    session["paciente_validado"] = paciente
    return jsonify(paciente), 200


@app.get("/api/paciente/habitacion/<path:habitacion>")
def pacientes_por_habitacion_api(habitacion):
    if session.get("usuario") is None:
        return jsonify({"ok": False, "mensaje": "Sesi\u00f3n requerida."}), 401
    room = re.sub(r"\s+", " ", habitacion.strip().upper())
    if not room:
        return jsonify({"ok": False, "mensaje": "Ingresa una habitaci\u00f3n."}), 400
    combined_match = re.fullmatch(r"([A-Z0-9]+)-([0-9]+)\s+Y\s+([0-9]+)", room)
    room_match = re.fullmatch(r"([A-Z0-9]+)(?:-([0-9]+))?", room)
    if not room_match and not combined_match:
        return jsonify({"ok": False, "mensaje": "Ingresa un n\u00famero de habitaci\u00f3n v\u00e1lido."}), 400
    usuario_historia = oracle_user_from_request()
    if not usuario_historia:
        return jsonify({"ok": False, "mensaje": ORACLE_AUTH_MESSAGE}), 428
    if not ORACLE_PASSWORD:
        return jsonify({"ok": False, "mensaje": "La consulta de pacientes no est\u00e1 configurada."}), 503
    try:
        if combined_match:
            room_number, first_bed, second_bed = combined_match.groups()
            exact_beds = {f"{room_number}-{first_bed}", f"{room_number}-{second_bed}", room}
        else:
            room_number = room_match.group(1)
            exact_beds = {f"{room_number}-{room_match.group(2)}"} if room_match.group(2) else None
        patients = buscar_por_habitacion(room_number, usuario_historia)
        with get_local_db_connection() as connection:
            for patient in patients:
                moved = connection.execute(
                    "SELECT habitacion_destino FROM Traslados WHERE documento=? ORDER BY id DESC LIMIT 1",
                    (patient["identificacion"],),
                ).fetchone()
                if moved and moved["habitacion_destino"]:
                    patient["cama"] = moved["habitacion_destino"]
                location_code = re.sub(r"\s+", " ", str(patient.get("cama") or "").strip().upper())
                mapped_location = _catalog_location(connection, location_code)[0] if location_code else None
                if mapped_location and "ubicaciones_ambiguas" in mapped_location:
                    mapped_location = None
                elif mapped_location:
                    location_code = mapped_location["ubicacion_codigo"]
                    patient["cama"] = location_code
                compatible_controls = connection.execute(
                    """SELECT id, codigo, serial, marca, estado FROM Controles
                        WHERE activo=1 AND UPPER(TRIM(marca))=UPPER(TRIM(?))
                        ORDER BY codigo""",
                    (mapped_location["marca_control_requerida"],),
                ).fetchall() if mapped_location else []
                active_loan = connection.execute(
                    """SELECT p.control_codigo, c.estado
                         FROM Prestamos p
                         LEFT JOIN Controles c ON c.id = p.control_id
                        WHERE p.documento = ? AND p.estado = 'ACTIVO'
                          AND UPPER(TRIM(COALESCE(p.habitacion_actual, p.habitacion, ''))) = ?
                        ORDER BY p.id DESC LIMIT 1""",
                    (patient["identificacion"], location_code),
                ).fetchone()
                patient["control_tv"] = {
                    "marca_requerida": mapped_location["marca_control_requerida"] if mapped_location else None,
                    "codigo": active_loan["control_codigo"] if active_loan else None,
                    "estado": active_loan["estado"] if active_loan else (
                        "DISPONIBLE" if any(item["estado"] == "DISPONIBLE" for item in compatible_controls) else "SIN_CONTROL_DISPONIBLE"
                    ),
                    "controles_compatibles": [
                        {"codigo": item["codigo"], "marca": item["marca"], "estado": item["estado"]}
                        for item in compatible_controls
                    ],
                }
        if exact_beds:
            def canonical_bed(value):
                normalized = re.sub(r"\s+", " ", str(value or "").strip().upper())
                concatenated = re.fullmatch(r"([0-9]{3})([0-9])", normalized)
                return f"{concatenated.group(1)}-{concatenated.group(2)}" if concatenated else normalized
            exact_matches = [patient for patient in patients if canonical_bed(patient.get("cama")) in exact_beds]
            if not exact_matches and patients:
                return jsonify({
                    "ok": False,
                    "mensaje": "El censo no identifica la cama individual para esta habitaci\u00f3n; consulta el cuarto completo o valida la cama en el censo.",
                }), 409
            patients = exact_matches
    except Exception:
        app.logger.exception("Error consultando pacientes por habitaci\u00f3n")
        return jsonify({"ok": False, "mensaje": "No fue posible consultar los pacientes de esa habitaci\u00f3n."}), 500
    if not patients:
        return jsonify({"ok": False, "mensaje": "No se encontraron pacientes registrados en esa habitaci\u00f3n."}), 404
    return jsonify({"ok": True, "habitacion": room, "pacientes": patients})


@app.get("/api/paciente/identificacion/<numero_identificacion>")
def paciente_por_identificacion_api(numero_identificacion):
    return respuesta_busqueda_paciente(numero_identificacion, "identificacion")


@app.get("/api/paciente/cama/<numero_cama>")
def paciente_por_cama_api(numero_cama):
    return respuesta_busqueda_paciente(numero_cama, "cama")


@app.get("/api/buscar-usuario")
def buscar_usuario_prueba():
    """Compatibilidad con la pantalla de consulta usando solo pacientes reales."""
    if session.get("usuario") is None:
        return jsonify({"encontrado": False, "mensaje": "Sesi\u00f3n requerida."}), 401
    criterio = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "document").strip()
    if not criterio:
        return jsonify({"encontrado": False, "mensaje": "Ingresa un dato para buscar."}), 400
    usuario_historia = oracle_user_from_request()
    if not usuario_historia:
        return jsonify({"encontrado": False, "mensaje": ORACLE_AUTH_MESSAGE}), 428
    if not ORACLE_PASSWORD:
        return jsonify({"encontrado": False, "mensaje": "La consulta de pacientes no est\u00e1 configurada."}), 503
    try:
        if tipo == "room":
            candidates = buscar_por_habitacion(criterio.upper(), usuario_historia)
            if len(candidates) > 1:
                return jsonify({"encontrado": False, "mensaje": "La habitaci\u00f3n tiene varios pacientes; selecciona uno en la b\u00fasqueda de pr\u00e9stamos.", "pacientes": candidates}), 409
            patient = candidates[0] if candidates else None
        else:
            patient = buscar_por_identificacion(criterio, usuario_historia)
    except Exception:
        app.logger.exception("Error consultando paciente para compatibilidad")
        return jsonify({"encontrado": False, "mensaje": "No fue posible consultar el sistema de pacientes."}), 500
    if patient is None:
        return jsonify({"encontrado": False, "mensaje": "No se encontr\u00f3 el paciente."}), 404
    with get_local_db_connection() as connection:
        moved = connection.execute("SELECT habitacion_destino FROM Traslados WHERE documento=? ORDER BY id DESC LIMIT 1", (patient["identificacion"],)).fetchone()
        if moved and moved["habitacion_destino"]:
            patient["cama"] = moved["habitacion_destino"]
        loan = connection.execute("SELECT p.*,c.estado AS estado_control FROM Prestamos p LEFT JOIN Controles c ON c.id=p.control_id WHERE p.documento=? AND p.estado='ACTIVO' AND COALESCE(p.habitacion_actual,p.habitacion)=? ORDER BY p.id DESC LIMIT 1", (patient["identificacion"], patient["cama"])).fetchone()
    session["paciente_validado"] = patient
    start = datetime.fromisoformat(loan["fecha_entrega"]) if loan else None
    hours = max(0, (datetime.now() - start).total_seconds() / 3600) if start else 0
    return jsonify({"encontrado": True, "paciente": {
        "nombre": patient["nombre_completo"], "cedula": patient["identificacion"], "tipo_identificacion": patient["tipo_identificacion"],
        "habitacion": patient["cama"], "control": loan["control_codigo"] if loan else "No asignado",
        "estado": loan["estado_control"] if loan else "Sin asignar", "fecha_entrega": loan["fecha_entrega"] if loan else None,
        "dias_con_control": max(1, math.ceil(hours / 24)) if loan else 0, "valor_diario": PRECIO_DIARIO,
        "valor_total": calcular_total(fecha_inicio=start, fecha_fin=datetime.now()) if start else 0,
    }})


@app.get("/api/controles-disponibles")
def controles_disponibles_api():
    if session.get("usuario") is None:
        return jsonify({"ok": False, "controles": [], "mensaje": "Sesión requerida."}), 401

    try:
        controls = listar_controles_disponibles(SQL_SERVER_CONNECTION_STRING)
    except Exception:
        app.logger.warning("SQL Server sin acceso; usando inventario local persistente")
        controls = []

    if not controls:
        controls = listar_controles_local_disponibles()
        mensaje = "Inventario inicial persistente cargado con 159 controles disponibles."
        return jsonify({"ok": True, "controles": controls, "mensaje": mensaje, "persistido": True})

    return jsonify({"ok": True, "controles": controls, "mensaje": None if controls else "No hay controles disponibles para asignar. Verifique el inventario.", "persistido": True})


@app.get("/api/inventario/controles-disponibles")
def inventario_controles_disponibles_api():
    """Devuelve los controles disponibles del inventario que usa el flujo de préstamos."""
    if session.get("usuario") is None:
        return jsonify({"ok": False, "controles": [], "mensaje": "Sesión requerida."}), 401
    controls = listar_controles_local_disponibles()
    return jsonify({
        "ok": True,
        "controles": controls,
        "mensaje": None if controls else "No hay controles disponibles en el inventario. Actualiza el inventario antes de continuar.",
        "persistido": True,
    })


@app.get("/api/catalogo/ubicaciones")
def catalogo_ubicaciones_api():
    if session.get("usuario") is None:
        return jsonify({"ok": False, "ubicaciones": [], "mensaje": "Sesi\u00f3n requerida."}), 401
    try:
        locations = listar_mapa_habitacion_control(SQL_SERVER_CONNECTION_STRING)
        source = "sqlserver_habitacion_control" if locations else None
    except Exception as error:
        app.logger.debug("Usando catálogo local de ubicaciones: %s", error)
        locations, source = [], None
    if not locations:
        with get_local_db_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM Habitaciones WHERE Activa=1 ORDER BY Servicio,Piso,Habitacion,Cama"
            ).fetchall()
        locations = [_map_local_location(row) for row in rows]
        source = "sqlite_local"
    return jsonify({
        "ok": True,
        "persistido": True,
        "fuente": source,
        "ubicaciones": locations,
    })


@app.get("/api/catalogo/ubicaciones/<ubicacion_codigo>")
def catalogo_ubicacion_api(ubicacion_codigo):
    if session.get("usuario") is None:
        return jsonify({"ok": False, "mensaje": "Sesi\u00f3n requerida."}), 401
    with get_local_db_connection() as connection:
        location, source = _catalog_location(connection, ubicacion_codigo)
    if location is None:
        return jsonify({"ok": False, "persistido": True, "mensaje": "No se encontr\u00f3 la ubicaci\u00f3n en el cat\u00e1logo."}), 404
    if "ubicaciones_ambiguas" in location:
        return jsonify({
            "ok": False,
            "persistido": True,
            "mensaje": "La habitaci\u00f3n tiene varias camas; selecciona la cama exacta.",
            "ubicaciones": location["ubicaciones_ambiguas"],
        }), 409
    return jsonify({"ok": True, "persistido": True, "fuente": source, "ubicacion": location})


@app.get("/api/catalogo/ubicaciones/<ubicacion_codigo>/controles")
def catalogo_controles_ubicacion_api(ubicacion_codigo):
    if session.get("usuario") is None:
        return jsonify({"ok": False, "controles": [], "mensaje": "Sesi\u00f3n requerida."}), 401

    code = ubicacion_codigo.strip().upper()
    with get_local_db_connection() as connection:
        location, source = _catalog_location(connection, code)
        if location is None:
            return jsonify({
                "ok": False, "controles": [], "persistido": True,
                "tipo_error": "MAPEO_UBICACION",
                "mensaje": "No existe una correspondencia para esta habitaci\u00f3n/cama en el cat\u00e1logo. Verifique el mapeo habitaci\u00f3n-marca; no es un problema de stock.",
            }), 404
        if "ubicaciones_ambiguas" in location:
            return jsonify({
                "ok": False,
                "controles": [],
                "persistido": True,
                "mensaje": "La habitaci\u00f3n tiene varias camas; selecciona la cama exacta.",
                "ubicaciones": location["ubicaciones_ambiguas"],
            }), 409
        required_brand = location["marca_control_requerida"]
        rows = connection.execute(
            """SELECT id, codigo, serial, marca, ubicacion_asignada, estado
                 FROM Controles
                WHERE activo=1 AND estado='DISPONIBLE'
                  AND UPPER(TRIM(marca))=UPPER(TRIM(?))
                ORDER BY codigo""",
            (required_brand,),
        ).fetchall()
        stock = connection.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN estado='DISPONIBLE' THEN 1 ELSE 0 END) AS disponibles,
                      SUM(CASE WHEN estado='PRESTADO' THEN 1 ELSE 0 END) AS en_uso,
                      SUM(CASE WHEN estado='PENDIENTE_DEVOLUCION' THEN 1 ELSE 0 END) AS pendientes
                 FROM Controles
                WHERE activo=1 AND UPPER(TRIM(marca))=UPPER(TRIM(?))""",
            (required_brand,),
        ).fetchone()
        controls = [
            {"id": row["id"], "codigo": row["codigo"], "serial": row["serial"],
             "marca": row["marca"], "ubicacion_asignada": row["ubicacion_asignada"],
             "estado": row["estado"]}
            for row in rows
        ]

    if controls:
        message = None
    elif not stock or not stock["total"]:
        message = f"La ubicaci\u00f3n est\u00e1 asociada a {required_brand}, pero no hay unidades de esa marca registradas en el inventario. Ingrese el stock real para poder prestar."
    else:
        message = (
            f"No hay controles {required_brand} disponibles en bodega. "
            f"Registrados: {stock['total']}; en uso: {stock['en_uso'] or 0}; "
            f"pendientes de devoluci\u00f3n: {stock['pendientes'] or 0}."
        )
    return jsonify({
        "ok": True, "ubicacion": location, "marca_requerida": required_brand, "fuente_catalogo": source,
        "controles": controls, "stock_marca": dict(stock) if stock else None,
        "mensaje": message, "persistido": True,
    })


@app.get("/api/inventario")
def inventario_api():
    if session.get("usuario") is None:
        return jsonify({"ok": False, "torres": [], "habitaciones": [], "mensaje": "Sesi\u00f3n requerida."}), 401
    with get_local_db_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM Habitaciones WHERE Activa=1 ORDER BY Servicio,Piso,Habitacion,Cama"
        ).fetchall()
    locations = [_map_local_location(row) for row in rows]
    rooms = [
        {"codigo": item["ubicacion_codigo"], "marca": item["marca_control_requerida"],
         "piso": item["piso"], "torre": item["servicio"], "habitacion": item["habitacion"],
         "cama": item["cama"], "marca_control_requerida": item["marca_control_requerida"], "control": None}
        for item in locations
    ]
    return jsonify({"ok": True, "persistido": True, "fuente": "sqlite_local", "torres": [],
                    "habitaciones": rooms, "mensaje": None})


@app.post("/api/prestamos")
def crear_prestamo_api():
    if session.get("usuario") is None:
        return jsonify({"ok": False, "mensaje": "Sesión requerida."}), 401
    data = request.get_json(silent=True) or {}
    documento = str(data.get("documento", "")).strip()
    nombre = str(data.get("nombre", "")).strip()
    recibe = str(data.get("recibe", "")).strip()
    parentesco = str(data.get("parentesco", "")).strip()
    exoneracion_categoria = str(data.get("exoneracion_categoria", "")).strip()
    responsable = str(data.get("responsable") or session.get("usuario", "")).strip()
    cama = str(data.get("habitacion", "")).strip().upper()
    try:
        control_id = int(data.get("control"))
    except (TypeError, ValueError):
        control_id = 0
    confirmed_physical = data.get("confirmar_control_fisico") is True
    confirmed_bed = data.get("confirmar_cama") is True
    if not all((documento, nombre, recibe, responsable, cama, control_id)):
        return jsonify({"ok": False, "mensaje": "Completa paciente, identificación, cama, control y persona que recibe."}), 400
    allowed_relationships = {"Paciente", "Hijo/a", "Cónyuge", "Padre/Madre", "Familiar", "Otro"}
    parentesco_key = unicodedata.normalize("NFKD", parentesco).encode("ascii", "ignore").decode("ascii").lower()
    if parentesco and parentesco_key not in {"paciente", "hijo/a", "conyuge", "padre/madre", "familiar", "otro"}:
        return jsonify({"ok": False, "mensaje": "Selecciona un parentesco válido."}), 400
    allowed_exemptions = {
        "medicina prepagada": "Medicina Prepagada",
        "plan complementario": "Plan Complementario",
        "habitante en situacion de calle": "Habitante en situaci\u00f3n de calle",
        "universidad nacional": "Universidad Nacional",
        "particulares": "Particulares",
        "poliza": "Póliza",
        "empleados y familiares": "Empleados y Familiares",
        "pacientes que pagan excedentes de habitacion": "Pacientes que pagan excedentes de habitación",
    }
    if exoneracion_categoria:
        exemption_key = unicodedata.normalize("NFKD", exoneracion_categoria).encode("ascii", "ignore").decode("ascii").strip().lower()
        if exemption_key not in allowed_exemptions:
            return jsonify({"ok": False, "mensaje": "Selecciona una categoría de exoneración válida."}), 400
        exoneracion_categoria = allowed_exemptions[exemption_key]
    valor_diario = 0 if exoneracion_categoria else PRECIO_DIARIO
    validated_patient = session.get("paciente_validado") or {}
    if str(validated_patient.get("identificacion", "")).strip() != documento:
        return jsonify({"ok": False, "mensaje": "Vuelve a buscar y validar al paciente antes de registrar el préstamo."}), 403
    if not confirmed_physical:
        return jsonify({"ok": False, "mensaje": "Confirma que identificaste el control físico que vas a entregar."}), 400
    if not confirmed_bed:
        return jsonify({"ok": False, "mensaje": "Confirma que la cama seleccionada corresponde a este paciente."}), 400
    nombre = validated_patient.get("nombre_completo") or nombre
    with get_local_db_connection() as connection:
        location, _catalog_source = _catalog_location(connection, cama)
    if isinstance(location, dict) and "ubicaciones_ambiguas" in location:
        return jsonify({"ok": False, "mensaje": "La habitaci\u00f3n tiene varias camas; selecciona la cama exacta."}), 409
    if location is None:
        return jsonify({"ok": False, "mensaje": "La ubicaci\u00f3n no existe en el cat\u00e1logo persistente."}), 404
    expected_room = str(validated_patient.get("cama", "")).strip().upper()
    selected_room = str(location.get("habitacion") or location["ubicacion_codigo"]).strip().upper()
    expected_location = expected_room
    selected_location = str(location.get("ubicacion_codigo") or cama).strip().upper()
    if expected_location == selected_location:
        expected_room = str(location.get("habitacion") or selected_location).strip().upper()
    expected_has_bed = bool(re.fullmatch(r"[A-Z0-9]+-[0-9]+", expected_location))
    selected_has_bed = bool(re.fullmatch(r"[A-Z0-9]+-[0-9]+", selected_location))
    if expected_has_bed and selected_location != expected_location:
        return jsonify({"ok": False, "mensaje": "La cama seleccionada no coincide con la cama exacta confirmada para el paciente."}), 409
    if not expected_has_bed and selected_has_bed:
        return jsonify({"ok": False, "mensaje": "El censo no informa la cama individual de este paciente; no se puede validar una asignación por cama."}), 409
    if re.fullmatch(r"[A-Z0-9]+-[0-9]+", expected_room):
        expected_room = expected_room.rsplit("-", 1)[0]
    if re.fullmatch(r"[A-Z0-9]+-[0-9]+", selected_room):
        selected_room = selected_room.rsplit("-", 1)[0]
    if not expected_room or selected_room != expected_room:
        return jsonify({"ok": False, "mensaje": "La cama seleccionada no pertenece a la habitación actual confirmada del paciente."}), 409
    now = datetime.now().isoformat(timespec="seconds")
    try:
        with get_local_db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM Prestamos WHERE documento=? AND estado='ACTIVO'", (documento,)).fetchone():
                return jsonify({"ok": False, "mensaje": "El paciente ya tiene un préstamo activo."}), 409
            control = connection.execute("SELECT * FROM Controles WHERE id=? AND activo=1", (control_id,)).fetchone()
            if control is None or control["estado"] != "DISPONIBLE":
                return jsonify({"ok": False, "mensaje": "El control ya no está disponible. Actualiza la lista antes de entregar."}), 409
            required_brand = str(location.get("marca_control_requerida") or "").strip().upper()
            if not required_brand or str(control["marca"]).strip().upper() != required_brand:
                return jsonify({"ok": False, "mensaje": "El control seleccionado no coincide con la marca requerida para esta habitaci\u00f3n."}), 409
            updated = connection.execute("UPDATE Controles SET estado='PRESTADO',ubicacion_asignada=?,updated_at=? WHERE id=? AND estado='DISPONIBLE'", (location["ubicacion_codigo"], now, control_id))
            if updated.rowcount != 1:
                return jsonify({"ok": False, "mensaje": "No se pudo reservar el control; permanece disponible."}), 409
            connection.execute("""INSERT INTO Prestamos(documento,nombre,habitacion,habitacion_actual,control_id,control_codigo,fecha_entrega,estado,responsable,responsable_entrega,recibe,valor_diario,valor_total,exoneracion_categoria,observaciones,confirmacion_cama,confirmacion_fisica)
                VALUES(?,?,?,?,?,?,?,'ACTIVO',?,?,?,?,0,?,'Cama y control confirmados físicamente por el responsable',1,1)""",
                (documento,nombre,location["ubicacion_codigo"],location["ubicacion_codigo"],control_id,control["codigo"],now,responsable,responsable,recibe,valor_diario,exoneracion_categoria or None))
            connection.execute(
                "UPDATE Prestamos SET parentesco=? WHERE documento=? AND fecha_entrega=? AND estado='ACTIVO'",
                (parentesco or None, documento, now),
            )
        sincronizar_prestamos_activos()
        return jsonify({"ok": True, "mensaje": "Préstamo exento registrado a $0." if exoneracion_categoria else "Entrega registrada correctamente.", "control": control["codigo"], "fecha_entrega": now, "exoneracion_categoria": exoneracion_categoria or None, "valor_diario": valor_diario})
    except sqlite3.Error:
        app.logger.exception("No se pudo guardar la entrega")
        return jsonify({"ok": False, "mensaje": "No se guardó la entrega; no se confirmó el préstamo."}), 500


@app.get("/api/dashboard/resumen")
def dashboard_resumen_api():
    if session.get("usuario") is None: return jsonify({"ok":False,"mensaje":"Sesi\u00f3n requerida."}),401
    with get_local_db_connection() as c: rows=c.execute("SELECT estado,COUNT(*) cantidad FROM Controles WHERE activo=1 GROUP BY estado").fetchall()
    counts={r["estado"]:r["cantidad"] for r in rows}
    return jsonify({"ok":True,"disponibles":counts.get("DISPONIBLE",0),"en_uso":counts.get("PRESTADO",0),"pendientes":counts.get("PENDIENTE_DEVOLUCION",0),"total":sum(counts.values())})

@app.get("/api/prestamos")
def prestamos_historial_api():
    if session.get("usuario") is None: return jsonify({"ok":False,"prestamos":[],"mensaje":"Sesi\u00f3n requerida."}),401
    now=datetime.now()
    with get_local_db_connection() as c: rows=c.execute("SELECT p.*,c.estado AS control_estado,c.marca AS control_marca FROM Prestamos p LEFT JOIN Controles c ON c.id=p.control_id ORDER BY p.fecha_entrega DESC,p.id DESC").fetchall()
    items=[]
    for r in rows:
        start=datetime.fromisoformat(r["fecha_entrega"]); end=datetime.fromisoformat(r["fecha_devolucion"]) if r["fecha_devolucion"] else now
        cost=0 if r["exoneracion_categoria"] else calcular_total(fecha_inicio=start,fecha_fin=end)
        items.append({"id":r["id"],"documento":r["documento"],"nombre":r["nombre"],"habitacion":r["habitacion"],"habitacion_actual":r["habitacion_actual"] or r["habitacion"],"control":r["control_codigo"],"marca":r["control_marca"],"fecha_entrega":r["fecha_entrega"],"fecha_devolucion":r["fecha_devolucion"],"estado":r["estado"],"estado_control":r["control_estado"],"responsable":r["responsable_entrega"] or r["responsable"],"recibe":r["recibe"],"parentesco":r["parentesco"],"exoneracion_categoria":r["exoneracion_categoria"],"valor":r["valor_total"] if r["estado"]!="ACTIVO" else cost})
    return jsonify({"ok":True,"prestamos":items})

@app.post("/api/prestamos/<int:loan_id>/devolucion")
def devolver_prestamo_api(loan_id):
    if session.get("usuario") is None: return jsonify({"ok":False,"mensaje":"Sesi\u00f3n requerida."}),401
    data=request.get_json(silent=True) or {}; recibe=str(data.get("recibe","")).strip()
    actor=str(data.get("responsable") or session.get("usuario","")).strip()
    if not recibe or not actor: return jsonify({"ok":False,"mensaje":"Indica quién entrega físicamente el control y el funcionario."}),400
    now=datetime.now().isoformat(timespec="seconds")
    try:
        with get_local_db_connection() as c:
            c.execute("BEGIN IMMEDIATE")
            loan=c.execute("SELECT * FROM Prestamos WHERE id=? AND estado='ACTIVO'",(loan_id,)).fetchone()
            if not loan: return jsonify({"ok":False,"mensaje":"Préstamo no activo o ya devuelto."}),404
            start=datetime.fromisoformat(loan["fecha_entrega"]); end=datetime.fromisoformat(now)
            amount=0 if loan["exoneracion_categoria"] else calcular_total(fecha_inicio=start,fecha_fin=end); hours=max(0,(end-start).total_seconds()/3600)
            updated=c.execute("UPDATE Controles SET estado='DISPONIBLE',ubicacion_asignada=NULL,updated_at=? WHERE id=? AND estado IN ('PRESTADO','PENDIENTE_DEVOLUCION')",(now,loan["control_id"]))
            if updated.rowcount!=1: return jsonify({"ok":False,"mensaje":"Inventario no confirma que el control esté prestado; devolución sin cambios."}),409
            c.execute("UPDATE Prestamos SET estado='DEVUELTO',fecha_devolucion=?,valor_total=?,horas_cobradas=?,recibe_devolucion=?,responsable_devolucion=? WHERE id=? AND estado='ACTIVO'",(now,amount,hours,recibe,actor,loan_id))
        sincronizar_prestamos_activos()
        return jsonify({"ok":True,"mensaje":("Devolución guardada. Servicio exento: $0 COP." if loan["exoneracion_categoria"] else "Devolución guardada. Total definitivo: "+format(amount,",.0f")+" COP."),"valor_total":amount,"horas":hours})
    except sqlite3.Error:
        app.logger.exception("Error guardando devolución")
        return jsonify({"ok":False,"mensaje":"No se guardó la devolución; se mantiene el estado anterior."}),500


@app.post("/api/traslados")
def crear_traslado_api():
    if session.get("usuario") is None:
        return jsonify({"ok": False, "mensaje": "Sesi\u00f3n requerida."}), 401
    data = request.get_json(silent=True) or {}
    doc = str(data.get("documento", "")).strip()
    origin = str(data.get("origen", "")).strip().upper()
    dest = str(data.get("destino", "")).strip().upper()
    old_recipient = str(data.get("recibe_control_anterior", "")).strip()
    old_relationship = str(data.get("parentesco_control_anterior", "")).strip()
    new_recipient = str(data.get("recibe_nuevo_control", "")).strip()
    new_relationship = str(data.get("parentesco_nuevo_control", "")).strip()
    observation = str(data.get("observacion", "")).strip()
    actor = str(data.get("responsable") or session.get("usuario", "")).strip()
    patient = session.get("paciente_validado") or {}
    if not doc or patient.get("identificacion") != doc:
        return jsonify({"ok": False, "mensaje": "Busca y valida al paciente por identificaci?n antes de registrar el traslado."}), 403
    try:
        new_id = int(data.get("nuevo_control")) if data.get("nuevo_control") else None
    except (TypeError, ValueError):
        new_id = None
    if not origin or not dest or origin == dest:
        return jsonify({"ok": False, "mensaje": "Indica habitaci?n y cama de origen y un destino distinto."}), 400
    allowed_relationships = {
        "paciente": "Paciente",
        "conyuge": "C\u00f3nyuge",
        "hijo/a": "Hijo/a",
        "familiar": "Familiar",
        "otro": "Otro",
    }
    for field_name, field_value in (("parentesco_control_anterior", old_relationship), ("parentesco_nuevo_control", new_relationship)):
        if field_value:
            relationship_key = unicodedata.normalize("NFKD", field_value).encode("ascii", "ignore").decode("ascii").strip().lower()
            if relationship_key not in allowed_relationships:
                return jsonify({"ok": False, "mensaje": "Selecciona un parentesco v\u00e1lido."}), 400
            if field_name == "parentesco_control_anterior":
                old_relationship = allowed_relationships[relationship_key]
            else:
                new_relationship = allowed_relationships[relationship_key]
    if new_id and (not new_recipient or not new_relationship):
        return jsonify({"ok": False, "mensaje": "Selecciona qui\u00e9n recibe el nuevo control y su parentesco."}), 400

    with get_local_db_connection() as connection:
        destination, _catalog_source = _catalog_location(connection, dest)
    if destination is None or "ubicaciones_ambiguas" in destination:
        return jsonify({"ok": False, "mensaje": "Destino inexistente o ambiguo; selecciona una cama exacta del cat\u00e1logo."}), 404

    now = datetime.now().isoformat(timespec="seconds")
    disposition = data.get("novedad_control")
    if disposition not in {"returned", "pending", "no_control"}:
        disposition = "returned" if data.get("devolucion_confirmada") is True else None
    try:
        with get_local_db_connection() as c:
            c.execute("BEGIN IMMEDIATE")
            loan = c.execute(
                "SELECT * FROM Prestamos WHERE documento=? AND estado='ACTIVO' ORDER BY id DESC LIMIT 1",
                (doc,),
            ).fetchone()
            if disposition is None:
                disposition = "pending" if loan else "no_control"
            returned = disposition == "returned"
            if disposition == "returned" and not old_recipient:
                return jsonify({"ok": False, "mensaje": "Indica qui\u00e9n entrega el control anterior."}), 400
            if disposition == "returned" and not old_relationship:
                return jsonify({"ok": False, "mensaje": "Selecciona el parentesco de quien entrega el control anterior."}), 400

            old = None
            if loan:
                if str(loan["habitacion_actual"] or loan["habitacion"] or "").strip().upper() != origin:
                    return jsonify({"ok": False, "mensaje": "El origen no coincide con la ubicaci?n del pr?stamo activo."}), 409
                old = c.execute(
                    "SELECT * FROM Controles WHERE id=? AND activo=1 AND estado IN ('PRESTADO','PENDIENTE_DEVOLUCION')",
                    (loan["control_id"],),
                ).fetchone()
                if old is None:
                    return jsonify({"ok": False, "mensaje": "El control anterior no figura prestado o pendiente en el inventario."}), 409
                if disposition == "no_control":
                    return jsonify({"ok": False, "mensaje": "El paciente tiene un pr?stamo activo; registra devoluci?n f?sica o devoluci?n pendiente."}), 409
            else:
                patient_location = str(patient.get("cama", "")).strip().upper()
                patient_room = patient_location.rsplit("-", 1)[0] if re.fullmatch(r"[A-Z0-9]+-[0-9]+", patient_location) else patient_location
                origin_room = origin.rsplit("-", 1)[0] if re.fullmatch(r"[A-Z0-9]+-[0-9]+", origin) else origin
                if patient_room != origin_room:
                    return jsonify({"ok": False, "mensaje": "El origen no coincide con la ubicaci?n actual confirmada del paciente."}), 409
                if disposition in {"returned", "pending"}:
                    return jsonify({"ok": False, "mensaje": "No existe un control anterior que pueda devolverse o quedar pendiente."}), 409

            new = None
            if new_id:
                new = c.execute("SELECT * FROM Controles WHERE id=? AND activo=1", (new_id,)).fetchone()
                if new is None or new["estado"] != "DISPONIBLE":
                    return jsonify({"ok": False, "mensaje": "El nuevo control ya no est? disponible; actualiza el inventario."}), 409
                required_brand = str(destination.get("marca_control_requerida") or "").strip().upper()
                if not required_brand or str(new["marca"]).strip().upper() != required_brand:
                    return jsonify({"ok": False, "mensaje": "El nuevo control no coincide con la marca requerida para el destino."}), 409

            if old is not None and returned:
                started = datetime.fromisoformat(loan["fecha_entrega"])
                hours = max(0, (datetime.fromisoformat(now) - started).total_seconds() / 3600)
                amount = 0 if loan["exoneracion_categoria"] else calcular_total(fecha_inicio=started, fecha_fin=datetime.fromisoformat(now))
                changed = c.execute(
                    "UPDATE Controles SET estado='DISPONIBLE',ubicacion_asignada=NULL,updated_at=? WHERE id=? AND estado IN ('PRESTADO','PENDIENTE_DEVOLUCION')",
                    (now, old["id"]),
                )
                if changed.rowcount != 1:
                    raise sqlite3.IntegrityError("El control anterior cambi? de estado durante la devoluci?n.")
                closed = c.execute(
                    "UPDATE Prestamos SET estado='DEVUELTO',fecha_devolucion=?,valor_total=?,horas_cobradas=?,recibe_devolucion=?,responsable_devolucion=? WHERE id=? AND estado='ACTIVO'",
                    (now, amount, hours, actor, actor, loan["id"]),
                )
                if closed.rowcount != 1:
                    raise sqlite3.IntegrityError("El pr?stamo anterior ya no est? activo.")
            elif old is not None:
                pending = c.execute(
                    "UPDATE Controles SET estado='PENDIENTE_DEVOLUCION',ubicacion_asignada=?,updated_at=? WHERE id=? AND estado IN ('PRESTADO','PENDIENTE_DEVOLUCION')",
                    (destination["ubicacion_codigo"], now, old["id"]),
                )
                moved = c.execute(
                    "UPDATE Prestamos SET habitacion_actual=? WHERE id=? AND estado='ACTIVO'",
                    (destination["ubicacion_codigo"], loan["id"]),
                )
                if pending.rowcount != 1 or moved.rowcount != 1:
                    raise sqlite3.IntegrityError("No se pudo conservar el pr?stamo anterior como pendiente.")

            if new is not None:
                changed = c.execute(
                    "UPDATE Controles SET estado='PRESTADO',ubicacion_asignada=?,updated_at=? WHERE id=? AND estado='DISPONIBLE'",
                    (destination["ubicacion_codigo"], now, new_id),
                )
                if changed.rowcount != 1:
                    raise sqlite3.IntegrityError("El nuevo control dej? de estar disponible.")
                c.execute("""INSERT INTO Prestamos(documento,nombre,habitacion,habitacion_actual,control_id,control_codigo,fecha_entrega,estado,responsable,responsable_entrega,recibe,parentesco,valor_diario,valor_total,observaciones,confirmacion_cama,confirmacion_fisica)
                    VALUES(?,?,?,?,?,?,?,'ACTIVO',?,?,?,?,?,0,'Cama y control asignados por el cat\u00e1logo durante el traslado',1,1)""",
                    (doc, patient.get("nombre_completo", ""), destination["ubicacion_codigo"], destination["ubicacion_codigo"], new_id, new["codigo"], now, actor, actor, new_recipient, new_relationship, PRECIO_DIARIO))

            old_id = old["id"] if old else None
            old_code = old["codigo"] if old else None
            note = {"returned": "Control devuelto f?sicamente", "pending": "Control pendiente de devoluci?n", "no_control": "Paciente no us? control"}[disposition]
            if observation:
                note += ": " + observation
            c.execute("""INSERT INTO Traslados(documento,habitacion_origen,habitacion_destino,control_id,control_codigo,fecha_movimiento,responsable,estado,observaciones,devolucion_confirmada,nuevo_control_id,recibe_control_anterior,confirmacion_fisica)
                VALUES(?,?,?,?,?,?,?,'REGISTRADO',?,?,?,?,?)""",
                (doc, origin, destination["ubicacion_codigo"], old_id, old_code, now, actor, note, int(returned), new_id, actor if returned else None, int(bool(new))))
        sincronizar_prestamos_activos()
        message = "Traslado registrado. " + note + "."
        if new is not None:
            message += " Nuevo control " + new["codigo"] + " entregado."
        return jsonify({"ok": True, "mensaje": message})
    except sqlite3.Error:
        app.logger.exception("No se pudo registrar el traslado")
        return jsonify({"ok": False, "mensaje": "No se guard? el traslado; se revirti? la operaci?n completa."}), 500


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/entrega_control", methods=["GET", "POST"])
def entrega_control():
    """Consulta una habitación y prepara el resumen de entrega del control."""
    resultado = None
    error = None
    habitacion_ingresada = ""
    dias_ingresados = "1"
    fecha_inicio_ingresada = ""

    if request.method == "POST":
        # Normalizamos el valor para aceptar entradas como " 301 ".
        habitacion_ingresada = request.form.get("habitacion", "").strip().upper()
        dias_ingresados = request.form.get("dias", "1").strip()
        fecha_inicio_ingresada = request.form.get("fecha_inicio", "").strip()

        try:
            # Si se informa fecha, ella tiene prioridad sobre el número de días.
            if fecha_inicio_ingresada:
                fecha_inicio = datetime.strptime(fecha_inicio_ingresada, "%Y-%m-%d").date()
                dias_transcurridos = (date.today() - fecha_inicio).days
            else:
                dias_transcurridos = int(dias_ingresados)

            if dias_transcurridos < 0:
                raise ValueError
        except ValueError:
            error = "Ingresa un número de días válido igual o mayor que cero."
        else:
            datos_habitacion = buscar_habitacion(habitacion_ingresada)
            if datos_habitacion is None:
                error = f"La habitación '{habitacion_ingresada}' no existe en el registro."
            else:
                resultado = {
                    "habitacion": habitacion_ingresada,
                    "marca": datos_habitacion["marca"],
                    "piso": datos_habitacion["piso"],
                    "paciente": datos_habitacion["paciente"],
                    "cedula": datos_habitacion["cedula"],
                    "dias": dias_transcurridos,
                    "fecha_entrega": date.today().strftime("%d/%m/%Y"),
                    "recibe_control": session.get("usuario", "Usuario de recepción"),
                    "total": calcular_total(
                        dias_transcurridos=dias_transcurridos,
                        fecha_inicio=fecha_inicio_ingresada or None,
                    ),
                }

    # Renderizamos la misma pantalla en GET y POST para conservar el resultado.
    with open("entrega_control.html", encoding="utf-8") as archivo:
        contenido = archivo.read()

    return render_template_string(
        contenido,
        resultado=resultado,
        error=error,
        habitacion_ingresada=habitacion_ingresada,
        dias_ingresados=dias_ingresados,
        fecha_inicio_ingresada=fecha_inicio_ingresada,
        precio_diario=PRECIO_DIARIO,
    )


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    mensaje = None
    es_error = False
    credenciales = None
    imagen_pingui = IMAGEN_PINGUI_FELIZ
    verificacion_pendiente = bool(session.get("recuperacion_pendiente"))
    usuario_pendiente = session.get("recuperacion_pendiente")
    correo_destino = USUARIOS_PRUEBA.get(usuario_pendiente, {}).get("correo")

    if request.method == "POST":
        accion = request.form.get("accion", "verificar")
        if accion == "verificar":
            session.pop("recuperacion_pendiente", None)
            verificacion_pendiente = False
            usuario = request.form.get("usuario", "").strip()
            cedula = request.form.get("cedula", "").strip()
            datos_usuario = USUARIOS_PRUEBA.get(usuario)
            if datos_usuario is None or datos_usuario["cedula"] != cedula:
                mensaje = "El usuario de Historia y la cédula no coinciden."
                es_error = True
                imagen_pingui = IMAGEN_PINGUI_ERROR
            else:
                session["recuperacion_pendiente"] = usuario
                verificacion_pendiente = True
                correo = datos_usuario.get("correo", "correo institucional registrado")
                correo_destino = correo
                mensaje = f"Enviamos una notificación simulada a {correo}. ¿Eres tú?"
        else:
            usuario = session.get("recuperacion_pendiente")
            if request.form.get("confirmacion") == "si" and usuario in USUARIOS_PRUEBA:
                session.pop("recuperacion_pendiente", None)
                session["recuperacion_exitosa"] = usuario
                return redirect(url_for("recuperacion_exitosa"))
            else:
                mensaje = "No se confirmó la solicitud de recuperación."
                es_error = True
                session.pop("recuperacion_pendiente", None)
                verificacion_pendiente = False

    with open("recuperar.html", encoding="utf-8") as archivo:
        contenido = archivo.read()

    return render_template_string(
        contenido,
        mensaje=mensaje,
        es_error=es_error,
        credenciales=credenciales,
        verificacion_pendiente=verificacion_pendiente,
        correo_destino=correo_destino,
        imagen_pingui=imagen_pingui,
    )


@app.get("/recuperacion-exitosa")
def recuperacion_exitosa():
    usuario = session.pop("recuperacion_exitosa", None)
    datos_usuario = USUARIOS_PRUEBA.get(usuario)
    if datos_usuario is None:
        return redirect(url_for("recuperar"))

    with open("recuperar.html", encoding="utf-8") as archivo:
        contenido = archivo.read()
    return render_template_string(
        contenido,
        mensaje="¡Datos recuperados!",
        es_error=False,
        credenciales={"usuario": usuario, "contrasena": datos_usuario["contrasena"]},
        verificacion_pendiente=False,
        correo_destino=datos_usuario.get("correo"),
        imagen_pingui=IMAGEN_RECUPERACION_FELIZ,
    )


@app.get("/api/usuarios/<cedula>")
def buscar_usuario(cedula):
    usuario = USUARIOS.get(cedula.strip())
    if usuario is None:
        return jsonify({"encontrado": False, "mensaje": "No encontramos un usuario con esa cédula."}), 404

    return jsonify({"encontrado": True, **usuario})


@app.post("/api/recuperar")
def solicitar_recuperacion():
    datos = request.get_json(silent=True) or {}
    cedula = str(datos.get("cedula", "")).strip()
    if cedula not in USUARIOS:
        return jsonify({"ok": False, "mensaje": "No encontramos un usuario con esa cédula."}), 404

    return jsonify({"ok": True, "mensaje": "Recuperación solicitada correctamente."})


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5001")), debug=False)
