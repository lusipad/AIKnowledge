FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AICODING_DB_URL=sqlite:///./runtime/aicoding_mvp.db
ENV AICODING_VECTOR_BACKEND=simple

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docs ./docs
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY README.md ./README.md

RUN mkdir -p /app/runtime

EXPOSE 8000

CMD ["sh", "-c", "python scripts/init_db.py && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
