import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.services.llm_validation import verify_llm_connection
from app.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify the configured LLM endpoint.')
    parser.add_argument('--prompt', default='Reply with ok only.')
    parser.add_argument('--max-tokens', type=int, default=32)
    args = parser.parse_args()

    settings = load_settings()
    result = verify_llm_connection(settings, prompt=args.prompt, max_tokens=args.max_tokens)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
