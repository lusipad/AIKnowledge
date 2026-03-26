from __future__ import annotations

from sqlalchemy import text

from app.database import engine
from app.services.database_admin import schema_drift_status
from app.settings import load_settings



def database_healthcheck() -> tuple[bool, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return True, 'ok'
    except Exception as exc:  # pragma: no cover - defensive path
        return False, str(exc)


def vector_store_healthcheck() -> dict:
    settings = load_settings()
    detail = {
        'backend': settings.vector_backend,
        'native_pgvector': False,
        'extension_installed': False,
        'vector_dimensions': settings.vector_dimensions,
    }
    if settings.vector_backend not in {'pgvector', 'postgres'}:
        return detail
    if engine.dialect.name != 'postgresql':
        return detail
    try:
        with engine.connect() as connection:
            installed = bool(connection.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar())
        detail['native_pgvector'] = True
        detail['extension_installed'] = installed
        return detail
    except Exception as exc:  # pragma: no cover - defensive path
        detail['error'] = str(exc)
        return detail


def database_readiness_status() -> tuple[bool, dict]:
    db_ok, db_detail = database_healthcheck()
    schema_ok = False
    schema_detail: dict | str
    if db_ok:
        schema_ok, schema_detail = schema_drift_status()
    else:
        schema_detail = {
            'schema_ready': False,
            'missing_tables': [],
            'expected_heads': [],
            'current_heads': [],
            'diffs': [],
            'error': 'database unavailable',
        }
    return db_ok and schema_ok, {
        'database': {'ok': db_ok, 'detail': db_detail},
        'schema': {'ok': schema_ok, 'detail': schema_detail},
        'vector_store': vector_store_healthcheck(),
    }
