from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, engine
from app.request_context import RequestContextMiddleware
from app.routers.audit import router as audit_router
from app.routers.config import router as config_router
from app.routers.context import router as context_router
from app.routers.evaluation import router as evaluation_router
from app.routers.feedback import router as feedback_router
from app.routers.knowledge import router as knowledge_router
from app.routers.llm import router as llm_router
from app.routers.retrieval import router as retrieval_router
from app.routers.sessions import router as sessions_router
from app.routers.ui import router as ui_router
from app.security import ApiKeyMiddleware
from app.services.bootstrap import seed_default_profiles
from app.services.health import database_healthcheck
from app.settings import load_settings


settings = load_settings()
STATIC_ROOT = Path(__file__).resolve().parent / 'static'


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    database = SessionLocal()
    try:
        seed_default_profiles(database)
    finally:
        database.close()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

if settings.api_key_enabled:
    app.add_middleware(ApiKeyMiddleware, api_key=settings.api_key)
app.add_middleware(RequestContextMiddleware)

app.include_router(sessions_router)
app.include_router(context_router)
app.include_router(knowledge_router)
app.include_router(llm_router)
app.include_router(retrieval_router)
app.include_router(config_router)
app.include_router(feedback_router)
app.include_router(audit_router)
app.include_router(evaluation_router)
app.include_router(ui_router)
app.mount('/static', StaticFiles(directory=STATIC_ROOT), name='static')


@app.get('/')
def root():
    current_settings = load_settings()
    return {
        'service': 'ai-coding-knowledge-memory-mvp',
        'status': 'ok',
        'docs': '/docs',
        'console': '/console',
        'version': current_settings.app_version,
        'env': current_settings.env,
        'auth_enabled': current_settings.api_key_enabled,
        'vector_backend': current_settings.vector_backend,
        'llm_configured': current_settings.llm_configured,
    }


@app.get('/healthz')
def healthz():
    current_settings = load_settings()
    db_ok, db_detail = database_healthcheck()
    return {
        'status': 'ok' if db_ok else 'degraded',
        'database': {'ok': db_ok, 'detail': db_detail},
        'vector_backend': current_settings.vector_backend,
        'auth_enabled': current_settings.api_key_enabled,
        'llm': {
            'configured': current_settings.llm_configured,
            'model': current_settings.llm_model,
            'base_url': current_settings.llm_base_url,
        },
        'version': current_settings.app_version,
    }


@app.get('/readyz')
def readyz():
    return healthz()
