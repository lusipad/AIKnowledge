run:
	PYTHONDONTWRITEBYTECODE=1 python3 -m uvicorn app.main:app --reload

init-db:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/init_db.py

test:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v

demo:
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/demo_flow.py

migrate:
	PYTHONDONTWRITEBYTECODE=1 alembic upgrade head
