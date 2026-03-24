import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

runtime_dir = ROOT_DIR / 'runtime'
runtime_dir.mkdir(exist_ok=True)
os.environ.setdefault('AICODING_DB_URL', 'sqlite:///./runtime/aicoding_mvp.db')

from app.database import Base, SessionLocal, engine
from app.services.bootstrap import seed_default_profiles


Base.metadata.create_all(bind=engine)
database = SessionLocal()
try:
    seed_default_profiles(database)
finally:
    database.close()

print('database initialized')
