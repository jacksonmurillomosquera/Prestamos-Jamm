from oracle_db import oracle_connection


SQL_POR_IDENTIFICACION = r"""
    SELECT TIPO_IDENTIFICACION, IDENTIFICACION, NOMBRE_COMPLETO, CAMA, DIAS_ESTANCIA
      FROM (
            SELECT DISTINCT D.TIPIDAV AS TIPO_IDENTIFICACION,
                   TRIM(C.PAC_PAC_RUT) AS IDENTIFICACION,
                   REGEXP_REPLACE(C.PAC_PAC_NOMBRE || ' ' || C.PAC_PAC_APELLPATER || ' ' || C.PAC_PAC_APELLMATER, '\s+', ' ') AS NOMBRE_COMPLETO,
                   TRIM(V.HABITACION) AS CAMA,
                   (SELECT GREATEST(1, TRUNC(SYSDATE) - TRUNC(MAX(E.ATC_EST_FECHAHOSPI)) + 1)
                      FROM ATC_ESTADIA E
                     WHERE E.PAC_PAC_NUMERO = C.PAC_PAC_NUMERO
                       AND (E.ATC_EST_FECEGRESO IS NULL OR E.ATC_EST_FECEGRESO >= TRUNC(SYSDATE))) AS DIAS_ESTANCIA
              FROM VWCENSOCAMAS V
              JOIN PAC_PACIENTE C ON C.PAC_PAC_NUMERO = V.ID_INTERNO_PACIENTE
              LEFT JOIN TAB_TIPOIDENT D ON D.TAB_TIPOIDENTCODIGO = C.PAC_PAC_TIPOIDENTCODIGO
             WHERE TRIM(C.PAC_PAC_RUT) = :identificacion
             ORDER BY CAMA
           )
     WHERE ROWNUM = 1
"""

SQL_POR_CAMA = r"""
    SELECT TIPO_IDENTIFICACION, IDENTIFICACION, NOMBRE_COMPLETO, CAMA, DIAS_ESTANCIA
      FROM (
            SELECT DISTINCT D.TIPIDAV AS TIPO_IDENTIFICACION,
                   TRIM(C.PAC_PAC_RUT) AS IDENTIFICACION,
                   REGEXP_REPLACE(
                       C.PAC_PAC_NOMBRE || ' ' || C.PAC_PAC_APELLPATER || ' ' || C.PAC_PAC_APELLMATER,
                       '\s+', ' '
                   ) AS NOMBRE_COMPLETO,
                   TRIM(V.HABITACION) AS CAMA,
                   (SELECT GREATEST(1, TRUNC(SYSDATE) - TRUNC(MAX(E.ATC_EST_FECHAHOSPI)) + 1)
                      FROM ATC_ESTADIA E
                     WHERE E.PAC_PAC_NUMERO = C.PAC_PAC_NUMERO
                       AND (E.ATC_EST_FECEGRESO IS NULL OR E.ATC_EST_FECEGRESO >= TRUNC(SYSDATE))) AS DIAS_ESTANCIA
              FROM VWCENSOCAMAS V
              JOIN PAC_PACIENTE C
                ON C.PAC_PAC_NUMERO = V.ID_INTERNO_PACIENTE
              LEFT JOIN TAB_TIPOIDENT D
                ON C.PAC_PAC_TIPOIDENTCODIGO = D.TAB_TIPOIDENTCODIGO
             WHERE UPPER(TRIM(V.HABITACION)) = UPPER(:cama)
             ORDER BY CAMA, NOMBRE_COMPLETO
           )
     WHERE ROWNUM = 1
"""

SQL_POR_HABITACION = r"""
    SELECT DISTINCT D.TIPIDAV AS TIPO_IDENTIFICACION,
           TRIM(C.PAC_PAC_RUT) AS IDENTIFICACION,
           REGEXP_REPLACE(
               C.PAC_PAC_NOMBRE || ' ' || C.PAC_PAC_APELLPATER || ' ' || C.PAC_PAC_APELLMATER,
               '\s+', ' '
           ) AS NOMBRE_COMPLETO,
           TRIM(V.HABITACION) AS CAMA,
           (SELECT GREATEST(1, TRUNC(SYSDATE) - TRUNC(MAX(E.ATC_EST_FECHAHOSPI)) + 1)
              FROM ATC_ESTADIA E
             WHERE E.PAC_PAC_NUMERO = C.PAC_PAC_NUMERO
               AND (E.ATC_EST_FECEGRESO IS NULL OR E.ATC_EST_FECEGRESO >= TRUNC(SYSDATE))) AS DIAS_ESTANCIA
      FROM VWCENSOCAMAS V
      JOIN PAC_PACIENTE C ON C.PAC_PAC_NUMERO = V.ID_INTERNO_PACIENTE
      LEFT JOIN TAB_TIPOIDENT D ON D.TAB_TIPOIDENTCODIGO = C.PAC_PAC_TIPOIDENTCODIGO
     WHERE REGEXP_SUBSTR(UPPER(TRIM(V.HABITACION)), '^[A-Z0-9]+') = UPPER(:habitacion)
        OR REGEXP_LIKE(
               UPPER(TRIM(V.HABITACION)),
               '^' || UPPER(:habitacion) || '(-[0-9]+([[:space:]]+Y[[:space:]]+[0-9]+)?)?$'
           )
        OR REGEXP_LIKE(
               UPPER(TRIM(V.HABITACION)),
               '^' || UPPER(:habitacion) || '[0-9]$'
           )
     ORDER BY CAMA, NOMBRE_COMPLETO
"""


def _buscar(sql: str, parametro: str, valor: str, usuario_historia: str | None) -> dict | None:
    with oracle_connection(usuario_historia) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, {parametro: valor})
            row = cursor.fetchone()

    if row is None:
        return None

    return {
        "tipo_identificacion": str(row[0]).strip() if row[0] is not None else "",
        "identificacion": str(row[1]).strip() if row[1] is not None else "",
        "nombre_completo": str(row[2]).strip() if row[2] is not None else "",
        "cama": str(row[3]).strip() if row[3] is not None else "",
        "dias_estancia": int(row[4]) if len(row) > 4 and row[4] is not None else None,
    }


def buscar_por_identificacion(identificacion: str, usuario_historia: str | None = None) -> dict | None:
    return _buscar(SQL_POR_IDENTIFICACION, "identificacion", identificacion.strip(), usuario_historia)


def buscar_por_cama(cama: str, usuario_historia: str | None = None) -> dict | None:
    return _buscar(SQL_POR_CAMA, "cama", cama.strip(), usuario_historia)


def buscar_por_habitacion(habitacion: str, usuario_historia: str | None = None) -> list[dict]:
    with oracle_connection(usuario_historia) as connection:
        with connection.cursor() as cursor:
            cursor.execute(SQL_POR_HABITACION, {"habitacion": habitacion.strip()})
            rows = cursor.fetchall()
    return [{
        "tipo_identificacion": str(row[0]).strip() if row[0] is not None else "",
        "identificacion": str(row[1]).strip() if row[1] is not None else "",
        "nombre_completo": str(row[2]).strip() if row[2] is not None else "",
        "cama": str(row[3]).strip() if row[3] is not None else "",
        "dias_estancia": int(row[4]) if len(row) > 4 and row[4] is not None else None,
    } for row in rows]
