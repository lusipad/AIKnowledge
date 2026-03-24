from collections.abc import Generator

from app.database import SessionLocal


def get_db() -> Generator:
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()

