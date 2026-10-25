import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    ORACLE_USER = os.getenv("ORACLE_USER", "")
    ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")
    ORACLE_DSN = os.getenv(
        "ORACLE_DSN",
        "(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(HOST=scan-clices)(PORT=1521)))"
        "(CONNECT_DATA=(SERVICE_NAME=hisces)))",
    )
    ORACLE_POOL_MIN = int(os.getenv("ORACLE_POOL_MIN", "1"))
    ORACLE_POOL_MAX = int(os.getenv("ORACLE_POOL_MAX", "5"))
    ORACLE_POOL_INCREMENT = int(os.getenv("ORACLE_POOL_INCREMENT", "1"))
    ORACLE_POOL_TIMEOUT = int(os.getenv("ORACLE_POOL_TIMEOUT", "60"))
    ORACLE_ROOM_QUERY = os.getenv("ORACLE_ROOM_QUERY", "").strip()
    # Configure la carpeta real del Instant Client para activar modo Thick.
    # Vacío permite usar modo Thin sin asumir una ruta local inexistente.
    ORACLE_CLIENT_LIB_DIR = os.getenv("ORACLE_CLIENT_LIB_DIR", "").strip()
    ORACLE_CONNECT_TIMEOUT = int(os.getenv("ORACLE_CONNECT_TIMEOUT", "3"))


def validate_oracle_config():
    if not Config.ORACLE_USER:
        raise RuntimeError("Falta configurar ORACLE_USER en el archivo .env o en el entorno.")
    if not Config.ORACLE_PASSWORD:
        raise RuntimeError("Falta configurar ORACLE_PASSWORD en el archivo .env o en el entorno.")
    if Config.ORACLE_POOL_MIN < 1 or Config.ORACLE_POOL_MAX < Config.ORACLE_POOL_MIN:
        raise RuntimeError("El rango del pool Oracle no es válido.")
    if Config.ORACLE_POOL_INCREMENT < 1:
        raise RuntimeError("ORACLE_POOL_INCREMENT debe ser mayor que cero.")
