def listar_ubicaciones(connection_string):
    import pyodbc

    with pyodbc.connect(connection_string, timeout=5) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT UbicacionCodigo, Servicio, Piso, Torre, Habitacion, Cama,
                      MarcaControlRequerida
                 FROM dbo.Habitaciones
                WHERE Activa = 1 AND UbicacionCodigo IS NOT NULL
                ORDER BY Servicio, Piso, Habitacion, Cama"""
        )
        rows = cursor.fetchall()
    return [
        {
            "ubicacion_codigo": row.UbicacionCodigo,
            "servicio": row.Servicio,
            "piso": row.Piso,
            "torre": row.Torre,
            "habitacion": row.Habitacion,
            "cama": row.Cama,
            "marca_control_requerida": row.MarcaControlRequerida,
        }
        for row in rows
    ]


def buscar_ubicacion(connection_string, ubicacion_codigo):
    import pyodbc

    with pyodbc.connect(connection_string, timeout=5) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT TOP (1) UbicacionCodigo, Servicio, Piso, Torre, Habitacion, Cama,
                      MarcaControlRequerida
                 FROM dbo.Habitaciones
                WHERE Activa = 1 AND UbicacionCodigo = ?""",
            ubicacion_codigo,
        )
        row = cursor.fetchone()
        if row is not None:
            return _map_location(row)

        cursor.execute(
            """SELECT TOP (2) UbicacionCodigo, Servicio, Piso, Torre, Habitacion, Cama,
                      MarcaControlRequerida
                 FROM dbo.Habitaciones
                WHERE Activa = 1 AND Habitacion = ?
                ORDER BY UbicacionCodigo""",
            ubicacion_codigo,
        )
        candidates = cursor.fetchall()
    if len(candidates) > 1:
        return {"ubicaciones_ambiguas": [_map_location(candidate) for candidate in candidates]}
    if not candidates:
        return None
    return _map_location(candidates[0])


def _map_location(row):
    return {
        "ubicacion_codigo": row.UbicacionCodigo,
        "servicio": row.Servicio,
        "piso": row.Piso,
        "torre": row.Torre,
        "habitacion": row.Habitacion,
        "cama": row.Cama,
        "marca_control_requerida": row.MarcaControlRequerida,
    }


def listar_mapa_habitacion_control(connection_string):
    """Read the editable room/brand map maintained in SQL Server Management Studio."""
    import pyodbc

    with pyodbc.connect(connection_string, timeout=3) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT UbicacionCodigo, Servicio, Piso, Torre, Habitacion, Cama,
                      MarcaControlRequerida
                 FROM dbo.HabitacionControl
                WHERE Activa=1
                ORDER BY Servicio, Piso, Habitacion, Cama"""
        )
        rows = cursor.fetchall()
    return [_map_location(row) for row in rows]


def buscar_habitacion_control(connection_string, ubicacion_codigo):
    """Resolve an exact bed or return all mapped beds for a shared room."""
    import pyodbc

    code = str(ubicacion_codigo).strip().upper()
    with pyodbc.connect(connection_string, timeout=3) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT UbicacionCodigo, Servicio, Piso, Torre, Habitacion, Cama,
                      MarcaControlRequerida
                 FROM dbo.HabitacionControl
                WHERE Activa=1 AND UPPER(LTRIM(RTRIM(UbicacionCodigo)))=?""",
            code,
        )
        row = cursor.fetchone()
        if row is not None:
            return _map_location(row)
        cursor.execute(
            """SELECT TOP (2) UbicacionCodigo, Servicio, Piso, Torre, Habitacion, Cama,
                      MarcaControlRequerida
                 FROM dbo.HabitacionControl
                WHERE Activa=1 AND UPPER(LTRIM(RTRIM(Habitacion)))=?
                ORDER BY UbicacionCodigo""",
            code,
        )
        candidates = cursor.fetchall()
    if len(candidates) > 1:
        return {"ubicaciones_ambiguas": [_map_location(row) for row in candidates]}
    return _map_location(candidates[0]) if candidates else None


def controles_disponibles_para_ubicacion(connection_string, ubicacion_codigo):
    import pyodbc

    try:
        with pyodbc.connect(connection_string, timeout=5) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT h.UbicacionCodigo, h.HabitacionId, h.MarcaControlRequerida
                     FROM dbo.Habitaciones h
                    WHERE h.Activa = 1 AND h.UbicacionCodigo = ?""",
                ubicacion_codigo,
            )
            location = cursor.fetchone()
            if location is None:
                return None, []

            cursor.execute(
                """SELECT c.ControlId, c.CodigoInventario, c.Serial, c.Marca,
                          h.UbicacionCodigo AS ubicacion_asignada,
                          c.Estado
                     FROM dbo.Controles c
                     LEFT JOIN dbo.Habitaciones h ON h.HabitacionId = c.HabitacionId
                    WHERE c.Activo = 1
                      AND c.Estado = N'DISPONIBLE'
                      AND UPPER(LTRIM(RTRIM(c.Marca))) = UPPER(LTRIM(RTRIM(?)))
                    ORDER BY c.CodigoInventario, c.Serial, c.ControlId""",
                location.MarcaControlRequerida,
            )
            rows = cursor.fetchall()
        return {
            "ubicacion_codigo": location.UbicacionCodigo,
            "habitacion_id": location.HabitacionId,
            "marca_control_requerida": location.MarcaControlRequerida,
        }, [
            {
                "id": row.ControlId,
                "codigo": row.CodigoInventario,
                "serial": row.Serial,
                "marca": row.Marca,
                "ubicacion_asignada": row.ubicacion_asignada,
                "estado": row.Estado,
            }
            for row in rows
        ]
    except Exception:
        return None, []


def listar_controles_disponibles(connection_string):
    import pyodbc

    try:
        with pyodbc.connect(connection_string, timeout=5) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT c.ControlId, c.CodigoInventario, c.Serial, c.Marca,
                          h.UbicacionCodigo AS ubicacion_asignada, c.Estado
                     FROM dbo.Controles c
                     LEFT JOIN dbo.Habitaciones h ON h.HabitacionId = c.HabitacionId
                    WHERE c.Activo = 1 AND c.Estado = N'DISPONIBLE'
                    ORDER BY c.CodigoInventario, c.Serial, c.ControlId"""
            )
            rows = cursor.fetchall()
        return [
            {
                "id": row.ControlId,
                "codigo": row.CodigoInventario,
                "serial": row.Serial,
                "marca": row.Marca,
                "ubicacion_asignada": row.ubicacion_asignada,
                "estado": row.Estado,
            }
            for row in rows
        ]
    except Exception:
        return []
