from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.database import Base, build_engine, engine, get_database_url, normalize_database_url
from app.services.bootstrap import seed_default_profiles


ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = ROOT_DIR / 'alembic.ini'
ALEMBIC_SCRIPT_LOCATION = ROOT_DIR / 'alembic'


def build_alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option('script_location', str(ALEMBIC_SCRIPT_LOCATION))
    config.set_main_option('sqlalchemy.url', normalize_database_url(database_url or get_database_url()))
    return config


def run_migrations(database_url: str | None = None, revision: str = 'head') -> None:
    command.upgrade(build_alembic_config(database_url), revision)


def required_tables() -> set[str]:
    return set(Base.metadata.tables.keys())


def database_schema_status(database_engine=engine) -> tuple[bool, list[str]]:
    inspector = inspect(database_engine)
    existing_tables = set(inspector.get_table_names())
    missing_tables = sorted(required_tables() - existing_tables)
    return not missing_tables, missing_tables


def ensure_database_ready(database_engine=engine) -> None:
    schema_ready, missing_tables = database_schema_status(database_engine)
    if schema_ready:
        return

    missing = ', '.join(missing_tables)
    raise RuntimeError(
        'database schema is not ready; missing tables: '
        f'{missing}. Run "python scripts/init_db.py" or "alembic upgrade head" first.'
    )


def initialize_database(database_url: str | None = None, *, seed_profiles: bool = True) -> None:
    normalized_url = normalize_database_url(database_url or get_database_url())
    run_migrations(normalized_url)
    if not seed_profiles:
        return

    bootstrap_engine = build_engine(normalized_url)
    session_factory = sessionmaker(
        bind=bootstrap_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    database = session_factory()
    try:
        seed_default_profiles(database)
    finally:
        database.close()
        bootstrap_engine.dispose()
