run:
	PYTHONDONTWRITEBYTECODE=1 python3 -m uvicorn app.main:app --reload

init-db:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/init_db.py

test:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v

demo:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/demo_flow.py

client-demo:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/http_client.py demo

run-extract-worker:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_extract_worker.py

verify-llm:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify_llm.py

evaluate:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/evaluate_system.py

benchmark:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmark_retrieval.py

check-schema:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_schema_drift.py

migrate:
	PYTHONDONTWRITEBYTECODE=1 alembic upgrade head
