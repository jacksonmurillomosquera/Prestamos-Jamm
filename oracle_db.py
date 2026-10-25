from contextlib import contextmanager
from threading import Lock
import time

import oracledb

from config import Config, validate_oracle_config

_pool = None
_pool_lock = Lock()
_client_lock = Lock()
_client_initialized = False

# ORA codes for incorrect/expired credentials or a locked account.
_INVALID_CREDENTIAL_CODES = {1005, 1017, 28000, 28001}
_SQL_HC_USER_NAME = """
    SELECT TRIM(u.FLD_USERNAME)
      FROM PRIV_ADM.TBL_USER u
     WHERE UPPER(TRIM(u.FLD_USERNAME)) = UPPER(:u)
        OR UPPER(TRIM(u.FLD_USERCODE)) = UPPER(:u)
     FETCH FIRST 1 ROWS ONLY
"""


def _initialize_oracle_client():
    """Initialize Thick mode once, before the first connection or pool."""
    global _client_initialized
    if _client_initialized:
        return
    with _client_lock:
        if _client_initialized:
            return
        client_dir = Config.ORACLE_CLIENT_LIB_DIR
        if client_dir:
            oracledb.init_oracle_client(lib_dir=client_dir)
        _client_initialized = True


def get_pool():
    global _pool

    if _pool is None:
        with _pool_lock:
            if _pool is None:
                validate_oracle_config()
                _initialize_oracle_client()
                _pool = oracledb.create_pool(
                    user=Config.ORACLE_USER,
                    password=Config.ORACLE_PASSWORD,
                    dsn=Config.ORACLE_DSN,
                    min=Config.ORACLE_POOL_MIN,
                    max=Config.ORACLE_POOL_MAX,
                    increment=Config.ORACLE_POOL_INCREMENT,
                    timeout=Config.ORACLE_POOL_TIMEOUT,
                    getmode=oracledb.POOL_GETMODE_WAIT,
                )
    return _pool


def validar_credenciales_historia_clinica(usuario, password):
    """Validate HIS credentials and fetch the display name in the same session."""
    user = str(usuario or "").strip()
    if not user or not password:
        return False, "invalid", None

    try:
        _initialize_oracle_client()
    except Exception:
        return False, "unavailable", None

    # Retry once for a transient connection failure. Credential errors are
    # returned immediately and are never written to application logs.
    for attempt in range(2):
        connection = None
        try:
            connection = oracledb.connect(
                user=user,
                password=password,
                dsn=Config.ORACLE_DSN,
                tcp_connect_timeout=Config.ORACLE_CONNECT_TIMEOUT,
            )
            full_name = None
            try:
                with connection.cursor() as cursor:
                    cursor.execute(_SQL_HC_USER_NAME, u=user)
                    row = cursor.fetchone()
                if row and row[0]:
                    full_name = " ".join(str(row[0]).split())[:120] or None
            except oracledb.DatabaseError:
                # A name lookup failure must not invalidate correct credentials.
                pass
            return True, None, full_name
        except oracledb.DatabaseError as error:
            details = error.args[0] if error.args else None
            code = getattr(details, "code", None)
            message = str(error)
            if code in _INVALID_CREDENTIAL_CODES or any(
                f"ORA-{item:05d}" in message for item in _INVALID_CREDENTIAL_CODES
            ):
                return False, "invalid", None
            if attempt == 0:
                time.sleep(0.6)
        except Exception:
            if attempt == 0:
                time.sleep(0.6)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    return False, "unavailable", None


@contextmanager
def oracle_connection(historia_usuario):
    usuario = str(historia_usuario or "").strip()
    if not usuario:
        raise ValueError(
            "Para poder realizar la consulta en la base de datos Oracle, "
            "por favor ingresa tu usuario de Historia Clínica."
        )
    connection = get_pool().acquire()
    try:
        # The pool uses a technical account. Propagate the operator ID to
        # Oracle for audit purposes, never as the connection credential.
        connection.client_identifier = usuario[:64]
        yield connection
    finally:
        try:
            connection.client_identifier = None
        except Exception:
            pass
        connection.close()


def close_pool():
    global _pool

    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
