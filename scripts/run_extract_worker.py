import argparse
import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import SessionLocal
from app.services.use_cases import process_pending_extract_tasks_data


def run_once(limit: int) -> dict:
    database = SessionLocal()
    try:
        payload = process_pending_extract_tasks_data(database, limit=limit)
        database.commit()
        return payload
    finally:
        database.close()


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the extraction worker against pending extract tasks.')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--poll-sec', type=float, default=2.0)
    args = parser.parse_args()

    exit_code = 0
    while True:
        payload = run_once(args.limit)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if payload['processed_count'] > 0:
            exit_code = 0
        if not args.loop:
            return exit_code
        time.sleep(max(0.5, args.poll_sec))


if __name__ == '__main__':
    raise SystemExit(main())
