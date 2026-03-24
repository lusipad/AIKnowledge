from __future__ import annotations

from sqlalchemy import text

from app.database import engine



def database_healthcheck() -> tuple[bool, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return True, 'ok'
    except Exception as exc:  # pragma: no cover - defensive path
        return False, str(exc)
