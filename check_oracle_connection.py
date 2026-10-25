import logging
import sys
from getpass import getpass

from oracle_db import close_pool, oracle_connection, validar_credenciales_historia_clinica


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    try:
        usuario = input("Usuario de Historia Clínica: ").strip()
        password = getpass("Contraseña de Historia Clínica: ")
        valid, reason = validar_credenciales_historia_clinica(usuario, password)
        if not valid:
            raise RuntimeError(
                "Usuario o contraseña de Historia Clínica incorrectos."
                if reason == "invalid"
                else "No fue posible conectar con Historia Clínica."
            )
        with oracle_connection(usuario) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM DUAL")
                result = cursor.fetchone()
        if result != (1,):
            raise RuntimeError("La consulta de verificación devolvió un resultado inesperado.")
        logger.info("Conexión Oracle verificada correctamente.")
        return 0
    except Exception:
        logger.exception("No fue posible verificar la conexión Oracle.")
        return 1
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
