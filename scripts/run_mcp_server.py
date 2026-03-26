import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from app.mcp_server import build_mcp_server


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the AIKnowledge MCP server.')
    parser.add_argument('--transport', choices=('stdio', 'streamable-http'), default='stdio')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--mount-path', default='/')
    parser.add_argument('--streamable-http-path', default='/mcp')
    parser.add_argument('--log-level', default='INFO')
    args = parser.parse_args()

    try:
        server = build_mcp_server(
            host=args.host,
            port=args.port,
            mount_path=args.mount_path,
            streamable_http_path=args.streamable_http_path,
            log_level=args.log_level,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    server.run(transport=args.transport)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
