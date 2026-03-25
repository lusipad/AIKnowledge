import shutil
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.database import Base, normalize_database_url
from app.models import ConfigProfile
from app.services.database_admin import (
    alembic_version_present,
    database_schema_status,
    initialize_database,
    schema_drift_status,
)


class DatabaseAdminTestCase(unittest.TestCase):
    def test_database_schema_status_reports_missing_tables(self):
        engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
        try:
            schema_ready, missing_tables = database_schema_status(engine)
        finally:
            engine.dispose()

        self.assertFalse(schema_ready)
        self.assertIn('conversation_session', missing_tables)

    def test_database_schema_status_reports_ready_after_schema_creation(self):
        engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
        try:
            Base.metadata.create_all(bind=engine)
            schema_ready, missing_tables = database_schema_status(engine)
        finally:
            Base.metadata.drop_all(bind=engine)
            engine.dispose()

        self.assertTrue(schema_ready)
        self.assertEqual(missing_tables, [])

    def test_initialize_database_runs_migrations_and_seeds_profiles(self):
        temp_dir = Path(tempfile.mkdtemp(prefix='aiknowledge-db-admin-'))
        database_url = normalize_database_url(f"sqlite:///{(temp_dir / 'init.db').as_posix()}")
        try:
            initialize_database(database_url)

            engine = create_engine(database_url, connect_args={'check_same_thread': False})
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
            database = session_factory()
            try:
                schema_ready, missing_tables = database_schema_status(engine)
                profile_count = len(database.scalars(select(ConfigProfile)).all())
            finally:
                database.close()
                engine.dispose()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertTrue(schema_ready)
        self.assertEqual(missing_tables, [])
        self.assertGreaterEqual(profile_count, 1)

    def test_initialize_database_stamps_existing_schema_without_recreating_tables(self):
        temp_dir = Path(tempfile.mkdtemp(prefix='aiknowledge-db-admin-stamp-'))
        database_url = normalize_database_url(f"sqlite:///{(temp_dir / 'stamp.db').as_posix()}")
        engine = create_engine(database_url, connect_args={'check_same_thread': False})
        try:
            Base.metadata.create_all(bind=engine)
            self.assertFalse(alembic_version_present(engine))
            engine.dispose()

            initialize_database(database_url, seed_profiles=False)

            validation_engine = create_engine(database_url, connect_args={'check_same_thread': False})
            try:
                self.assertTrue(alembic_version_present(validation_engine))
            finally:
                validation_engine.dispose()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_schema_drift_status_reports_in_sync_after_initialize(self):
        temp_dir = Path(tempfile.mkdtemp(prefix='aiknowledge-db-admin-drift-ok-'))
        database_url = normalize_database_url(f"sqlite:///{(temp_dir / 'drift_ok.db').as_posix()}")
        try:
            initialize_database(database_url, seed_profiles=False)

            engine = create_engine(database_url, connect_args={'check_same_thread': False})
            try:
                schema_ok, detail = schema_drift_status(engine, database_url=database_url)
            finally:
                engine.dispose()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertTrue(schema_ok)
        self.assertEqual(detail['diffs'], [])
        self.assertEqual(detail['current_heads'], detail['expected_heads'])

    def test_schema_drift_status_reports_extra_table_drift(self):
        temp_dir = Path(tempfile.mkdtemp(prefix='aiknowledge-db-admin-drift-bad-'))
        database_url = normalize_database_url(f"sqlite:///{(temp_dir / 'drift_bad.db').as_posix()}")
        try:
            initialize_database(database_url, seed_profiles=False)

            engine = create_engine(database_url, connect_args={'check_same_thread': False})
            try:
                with engine.begin() as connection:
                    connection.execute(text('CREATE TABLE drift_only_table (id INTEGER PRIMARY KEY)'))
                schema_ok, detail = schema_drift_status(engine, database_url=database_url)
            finally:
                engine.dispose()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertFalse(schema_ok)
        self.assertTrue(any('drift_only_table' in diff for diff in detail['diffs']))
