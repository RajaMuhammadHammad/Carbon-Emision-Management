import os
import logging
import pyodbc
from dotenv import load_dotenv

# Load local .env if present (ignored on Cloud Run)
load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _clean_secret(value: str) -> str:
    """Clean any unwanted characters from secrets/env vars."""
    if value is None:
        return ""
    value = str(value).replace("\r", "").replace("\n", "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    if value.lower().startswith("-n "):
        value = value[3:].strip()
    return value


def get_db_connection():
    """Return a pyodbc connection using DB_CONN_STR env var."""
    conn_str = _clean_secret(os.getenv("DB_CONN_STR"))

    if not conn_str:
        raise RuntimeError("Missing required env var: DB_CONN_STR")

    try:
        conn = pyodbc.connect(conn_str, timeout=30)
        logger.info("Database connection successful.")
        return conn
    except pyodbc.Error:
        logger.exception("Database connection failed (pyodbc).")
        raise
