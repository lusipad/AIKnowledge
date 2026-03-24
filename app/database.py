import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DEFAULT_SQLITE_URL = 'sqlite:///./aicoding_mvp.db'


def _ensure_sqlite_parent_dir(database_url: str) -> str:
    if not database_url.startswith('sqlite:///'):
        return database_url
    if database_url in {'sqlite://', 'sqlite:///:memory:', 'sqlite+pysqlite:///:memory:'} or ':memory:' in database_url:
        return database_url

    database_path = database_url.replace('sqlite:///', '', 1)
    database_file = Path(database_path)
    if not database_file.is_absolute():
        database_file = Path.cwd() / database_file
    database_file.parent.mkdir(parents=True, exist_ok=True)
    return database_url


def normalize_database_url(database_url: str) -> str:
    if not database_url:
        return DEFAULT_SQLITE_URL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    if database_url.startswith('postgresql://') and '+psycopg' not in database_url:
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    return _ensure_sqlite_parent_dir(database_url)


def get_database_url() -> str:
    return normalize_database_url(os.getenv('AICODING_DB_URL', DEFAULT_SQLITE_URL))


DATABASE_URL = get_database_url()


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    normalized_url = normalize_database_url(database_url)
    engine_kwargs = {'pool_pre_ping': True}
    if normalized_url.startswith('sqlite'):
        engine_kwargs['connect_args'] = {'check_same_thread': False}
    else:
        pool_size = int(os.getenv('AICODING_DB_POOL_SIZE', '5'))
        max_overflow = int(os.getenv('AICODING_DB_MAX_OVERFLOW', '10'))
        engine_kwargs['pool_size'] = pool_size
        engine_kwargs['max_overflow'] = max_overflow
    return create_engine(normalized_url, **engine_kwargs)


engine = build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
