import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import build_engine, get_database_url
from app.services.database_admin import schema_drift_status


def main() -> int:
    database_url = get_database_url()
    database_engine = build_engine(database_url)
    try:
        schema_ok, detail = schema_drift_status(database_engine, database_url=database_url)
    finally:
        database_engine.dispose()

    payload = {
        'status': 'ok' if schema_ok else 'drifted',
        'schema': detail,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if schema_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
