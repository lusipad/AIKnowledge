from __future__ import annotations

from sqlalchemy import text

from app.database import engine
from app.services.database_admin import schema_drift_status



def database_healthcheck() -> tuple[bool, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return True, 'ok'
    except Exception as exc:  # pragma: no cover - defensive path
        return False, str(exc)


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
    }
