import argparse
from collections import Counter
from datetime import datetime, timezone
import os
import sqlite3

from dotenv import load_dotenv

from catalogo_controles import CATALOGO_UBICACIONES, DUPLICADOS_CATALOGO

load_dotenv()

SQLSERVER_CONNECTION = os.getenv(
    "PRESTAMOS_SQLSERVER_CONNECTION",
    "Driver={ODBC Driver 17 for SQL Server};"
    "Server=localhost\\SQLEXPRESS;"
    "Database=PrestamosCES;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;",
)

CATALOG_COLUMNS = {
    "Servicio": "TEXT",
    "Torre": "TEXT",
    "Habitacion": "TEXT",
    "Cama": "TEXT",
    "UbicacionCodigo": "TEXT",
    "MarcaControlRequerida": "TEXT",
    "CreatedAt": "TEXT",
    "UpdatedAt": "TEXT",
}


def _report():
    return {
        "procesadas": len(CATALOGO_UBICACIONES),
        "insertadas": 0,
        "actualizadas": 0,
        "omitidas_por_error": 0,
        "duplicados_detectados": len(DUPLICADOS_CATALOGO),
        "ubicaciones_no_interpretadas": [],
        "por_servicio": Counter(),
        "por_marca": Counter(),
        "errores": [],
    }


def _catalog_values(codigo, data):
    return (
        codigo,
        data["piso"],
        data["servicio"],
        data["torre"],
        data["habitacion"],
        data["cama"],
        data["marca_control_requerida"],
    )


def _add_sqlite_columns(connection):
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(Habitaciones)").fetchall()
    }
    for name, data_type in CATALOG_COLUMNS.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE Habitaciones ADD COLUMN {name} {data_type}")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS UX_Habitaciones_ServicioUbicacion "
        "ON Habitaciones (Servicio, UbicacionCodigo) "
        "WHERE Servicio IS NOT NULL AND UbicacionCodigo IS NOT NULL"
    )


def _ensure_sqlite_physical_inventory(connection):
    connection.execute(
        """CREATE TABLE IF NOT EXISTS Controles (
            ControlId INTEGER PRIMARY KEY AUTOINCREMENT,
            CodigoInventario TEXT UNIQUE,
            Serial TEXT,
            HabitacionId INTEGER,
            Marca TEXT NOT NULL,
            Estado TEXT NOT NULL DEFAULT 'SIN_VERIFICAR'
                CHECK (Estado IN ('DISPONIBLE','PRESTADO','FUERA_SERVICIO','SIN_VERIFICAR')),
            Activo INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (HabitacionId) REFERENCES Habitaciones(HabitacionId)
        )"""
    )
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(Controles)").fetchall()
    }
    if "CodigoInventario" not in columns:
        connection.execute("ALTER TABLE Controles ADD COLUMN CodigoInventario TEXT")
    if "Serial" not in columns:
        connection.execute("ALTER TABLE Controles ADD COLUMN Serial TEXT")
    if "Estado" not in columns:
        connection.execute("ALTER TABLE Controles ADD COLUMN Estado TEXT NOT NULL DEFAULT 'SIN_VERIFICAR'")
    if "Activo" not in columns:
        connection.execute("ALTER TABLE Controles ADD COLUMN Activo INTEGER NOT NULL DEFAULT 1")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS UX_Controles_CodigoInventario "
        "ON Controles (CodigoInventario) WHERE CodigoInventario IS NOT NULL"
    )


def seed_sqlite(database_path):
    connection = sqlite3.connect(database_path)
    report = _report()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS Habitaciones (
                HabitacionId INTEGER PRIMARY KEY AUTOINCREMENT,
                Numero TEXT NOT NULL UNIQUE,
                Piso TEXT NOT NULL,
                Servicio TEXT,
                Activa INTEGER NOT NULL DEFAULT 1
            )"""
        )
        _add_sqlite_columns(connection)
        _ensure_sqlite_physical_inventory(connection)
        connection.execute("BEGIN")

        for codigo, data in CATALOGO_UBICACIONES.items():
            if codigo in DUPLICADOS_CATALOGO:
                report["omitidas_por_error"] += 1
                continue
            if not data["servicio"] or not data["habitacion"] or not data["ubicacion_codigo"]:
                report["ubicaciones_no_interpretadas"].append(codigo)
                report["omitidas_por_error"] += 1
                continue

            values = _catalog_values(codigo, data)
            existing_rows = connection.execute(
                "SELECT HabitacionId, CreatedAt FROM Habitaciones "
                "WHERE Numero = ? OR (Servicio = ? AND UbicacionCodigo = ?) ORDER BY HabitacionId",
                (codigo, data["servicio"], codigo),
            ).fetchall()
            if len(existing_rows) > 1:
                report["duplicados_detectados"] += len(existing_rows) - 1
            existing = existing_rows[0] if existing_rows else None
            if existing:
                connection.execute(
                          """UPDATE Habitaciones SET Piso=?, Servicio=?, Torre=?, Habitacion=?, Cama=?,
                              UbicacionCodigo=?, MarcaControlRequerida=?,
                       CreatedAt=COALESCE(CreatedAt, ?), UpdatedAt=?
                       WHERE HabitacionId=?""",
                    (values[1], values[2], values[3], data["habitacion"], data["cama"], codigo,
                     data["marca_control_requerida"], now, now, existing[0]),
                )
                report["actualizadas"] += 1
            else:
                connection.execute(
                    """INSERT INTO Habitaciones
                              (Numero, Piso, Servicio, Torre, Habitacion, Cama, UbicacionCodigo,
                        MarcaControlRequerida, Activa, CreatedAt, UpdatedAt)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                          (codigo, data["piso"], data["servicio"], data["torre"], data["habitacion"],
                     data["cama"], codigo, data["marca_control_requerida"], now, now),
                )
                report["insertadas"] += 1
            report["por_servicio"][data["servicio"]] += 1
            report["por_marca"][data["marca_control_requerida"]] += 1

        connection.commit()
        report["controles_fisicos_creados"] = 0
        report["controles_fisicos_modificados"] = 0
        report["controles_fisicos_sin_verificar"] = connection.execute(
            "SELECT COUNT(*) FROM Controles WHERE Estado='SIN_VERIFICAR' AND Activo=1"
        ).fetchone()[0]
        return report
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _add_sqlserver_columns(cursor):
    sql_types = {
        "Servicio": "NVARCHAR(30) NULL",
        "Torre": "NVARCHAR(20) NULL",
        "Habitacion": "NVARCHAR(30) NULL",
        "Cama": "NVARCHAR(20) NULL",
        "UbicacionCodigo": "NVARCHAR(30) NULL",
        "MarcaControlRequerida": "NVARCHAR(20) NULL",
        "CreatedAt": "DATETIME2 NULL",
        "UpdatedAt": "DATETIME2 NULL",
    }
    for name, sql_type in sql_types.items():
        cursor.execute(
            f"IF COL_LENGTH('dbo.Habitaciones', '{name}') IS NULL "
            f"ALTER TABLE dbo.Habitaciones ADD {name} {sql_type}"
        )
    cursor.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='UX_Habitaciones_ServicioUbicacion' "
        "AND object_id=OBJECT_ID('dbo.Habitaciones')) "
        "CREATE UNIQUE INDEX UX_Habitaciones_ServicioUbicacion "
        "ON dbo.Habitaciones(Servicio,UbicacionCodigo) WHERE Servicio IS NOT NULL AND UbicacionCodigo IS NOT NULL"
    )


def _ensure_sqlserver_physical_inventory(cursor):
    cursor.execute(
        """IF OBJECT_ID('dbo.Controles', 'U') IS NULL
            CREATE TABLE dbo.Controles (
                ControlId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Controles PRIMARY KEY,
                CodigoInventario NVARCHAR(50) NULL,
                Serial NVARCHAR(80) NULL,
                HabitacionId INT NULL,
                Marca NVARCHAR(30) NOT NULL,
                Estado NVARCHAR(20) NOT NULL CONSTRAINT DF_Controles_Estado DEFAULT N'SIN_VERIFICAR',
                Activo BIT NOT NULL CONSTRAINT DF_Controles_Activo DEFAULT 1,
                CONSTRAINT FK_Controles_Habitaciones FOREIGN KEY (HabitacionId)
                    REFERENCES dbo.Habitaciones(HabitacionId),
                CONSTRAINT CK_Controles_Estado CHECK
                    (Estado IN (N'DISPONIBLE',N'PRESTADO',N'FUERA_SERVICIO',N'SIN_VERIFICAR'))
            )"""
    )
    cursor.execute(
        "IF COL_LENGTH('dbo.Controles', 'CodigoInventario') IS NULL "
        "ALTER TABLE dbo.Controles ADD CodigoInventario NVARCHAR(50) NULL"
    )
    cursor.execute(
        "IF COL_LENGTH('dbo.Controles', 'Serial') IS NULL "
        "ALTER TABLE dbo.Controles ADD Serial NVARCHAR(80) NULL"
    )
    cursor.execute(
        "IF COL_LENGTH('dbo.Controles', 'Estado') IS NULL "
        "ALTER TABLE dbo.Controles ADD Estado NVARCHAR(20) NOT NULL "
        "CONSTRAINT DF_Controles_Estado DEFAULT N'SIN_VERIFICAR' WITH VALUES"
    )
    cursor.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='CK_Controles_Estado' "
        "AND parent_object_id=OBJECT_ID('dbo.Controles')) "
        "ALTER TABLE dbo.Controles ADD CONSTRAINT CK_Controles_Estado CHECK "
        "(Estado IN (N'DISPONIBLE',N'PRESTADO',N'FUERA_SERVICIO',N'SIN_VERIFICAR'))"
    )
    cursor.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='UX_Controles_CodigoInventario' "
        "AND object_id=OBJECT_ID('dbo.Controles')) "
        "CREATE UNIQUE INDEX UX_Controles_CodigoInventario ON dbo.Controles(CodigoInventario) "
        "WHERE CodigoInventario IS NOT NULL"
    )


def seed_sqlserver(connection_string):
    import pyodbc

    connection = pyodbc.connect(connection_string, autocommit=False)
    report = _report()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        cursor = connection.cursor()
        _add_sqlserver_columns(cursor)
        _ensure_sqlserver_physical_inventory(cursor)
        for codigo, data in CATALOGO_UBICACIONES.items():
            if codigo in DUPLICADOS_CATALOGO:
                report["omitidas_por_error"] += 1
                continue
            if not data["servicio"] or not data["habitacion"] or not data["ubicacion_codigo"]:
                report["ubicaciones_no_interpretadas"].append(codigo)
                report["omitidas_por_error"] += 1
                continue

            cursor.execute(
                "SELECT TOP (2) HabitacionId FROM dbo.Habitaciones "
                "WHERE Numero=? OR (Servicio=? AND UbicacionCodigo=?) ORDER BY HabitacionId",
                codigo, data["servicio"], codigo,
            )
            rows = cursor.fetchall()
            if len(rows) > 1:
                report["duplicados_detectados"] += len(rows) - 1
            row = rows[0] if rows else None
            if row:
                cursor.execute(
                          """UPDATE dbo.Habitaciones SET Numero=?, Piso=?, Servicio=?, Torre=?, Habitacion=?,
                              Cama=?, UbicacionCodigo=?, MarcaControlRequerida=?,
                       CreatedAt=COALESCE(CreatedAt, ?), UpdatedAt=?
                       WHERE HabitacionId=?""",
                    codigo, data["piso"], data["servicio"], data["torre"], data["habitacion"],
                    data["cama"], codigo, data["marca_control_requerida"], now, now, row[0],
                )
                report["actualizadas"] += 1
            else:
                cursor.execute(
                    """INSERT INTO dbo.Habitaciones
                              (Numero, Piso, Servicio, Torre, Habitacion, Cama, UbicacionCodigo,
                        MarcaControlRequerida, Activa, CreatedAt, UpdatedAt)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                          codigo, data["piso"], data["servicio"], data["torre"], data["habitacion"],
                    data["cama"], codigo, data["marca_control_requerida"], now, now,
                )
                report["insertadas"] += 1
            report["por_servicio"][data["servicio"]] += 1
            report["por_marca"][data["marca_control_requerida"]] += 1

        connection.commit()
        report["controles_fisicos_creados"] = 0
        report["controles_fisicos_modificados"] = 0
        cursor.execute("SELECT COUNT_BIG(*) FROM dbo.Controles WHERE Estado=N'SIN_VERIFICAR' AND Activo=1")
        report["controles_fisicos_sin_verificar"] = cursor.fetchone()[0]
        return report
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def print_report(report, database_label):
    print(f"Motor: {database_label}")
    for key in ("procesadas", "insertadas", "actualizadas", "omitidas_por_error", "duplicados_detectados"):
        print(f"{key}: {report[key]}")
    print("controles_fisicos_creados: 0")
    print("controles_fisicos_modificados: 0")
    print(f"controles_fisicos_sin_verificar (no seleccionables): {report.get('controles_fisicos_sin_verificar', 0)}")
    print(f"ubicaciones_no_interpretadas: {report['ubicaciones_no_interpretadas']}")
    print(f"por_servicio: {dict(sorted(report['por_servicio'].items()))}")
    print(f"por_marca: {dict(sorted(report['por_marca'].items()))}")
    for error in report["errores"]:
        print(f"error: {error}")


def main():
    parser = argparse.ArgumentParser(description="Carga el catálogo oficial de ubicaciones y marcas requeridas.")
    parser.add_argument("--sqlite", metavar="ARCHIVO", help="Puebla una base SQLite existente o nueva.")
    args = parser.parse_args()

    if args.sqlite:
        report = seed_sqlite(args.sqlite)
        label = f"SQLite ({args.sqlite})"
    else:
        report = seed_sqlserver(SQLSERVER_CONNECTION)
        label = "SQL Server"
    print_report(report, label)


if __name__ == "__main__":
    main()
