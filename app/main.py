from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal, engine
from app.request_context import RequestContextMiddleware
from app.routers.auth import router as auth_router
from app.routers.audit import router as audit_router
from app.routers.config import router as config_router
from app.routers.context import router as context_router
from app.routers.evaluation import router as evaluation_router
from app.routers.feedback import router as feedback_router
from app.routers.iam import router as iam_router
from app.routers.knowledge import router as knowledge_router
from app.routers.llm import router as llm_router
from app.routers.retrieval import router as retrieval_router
from app.routers.sessions import router as sessions_router
from app.routers.ui import router as ui_router
from app.security import AuthenticationMiddleware
from app.services.bootstrap import seed_default_profiles
from app.services.database_admin import ensure_database_ready
from app.services.health import database_readiness_status
from app.settings import load_settings


settings = load_settings()
STATIC_ROOT = Path(__file__).resolve().parent / 'static'


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_database_ready()
    database = SessionLocal()
    try:
        seed_default_profiles(database)
    finally:
        database.close()
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
if settings.auth_enabled:
    app.add_middleware(
        AuthenticationMiddleware,
        api_keys=settings.configured_api_keys,
        api_key_roles=settings.api_key_roles,
        settings=settings,
    )

app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(context_router)
app.include_router(knowledge_router)
app.include_router(llm_router)
app.include_router(retrieval_router)
app.include_router(config_router)
app.include_router(feedback_router)
app.include_router(audit_router)
app.include_router(evaluation_router)
app.include_router(iam_router)
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
        'auth_enabled': current_settings.auth_enabled,
        'vector_backend': current_settings.vector_backend,
        'llm_configured': current_settings.llm_configured,
    }


@app.get('/healthz')
def healthz():
    current_settings = load_settings()
    readiness_ok, readiness_detail = database_readiness_status()
    return {
        'status': 'ok' if readiness_ok else 'degraded',
        'database': readiness_detail['database'],
        'schema': readiness_detail['schema'],
        'vector_backend': current_settings.vector_backend,
        'vector_store': readiness_detail['vector_store'],
        'auth_enabled': current_settings.auth_enabled,
        'auth': {
            'api_key_enabled': current_settings.api_key_enabled,
            'iam_enabled': current_settings.iam_enabled,
            'issuer': current_settings.iam_issuer,
            'audience': current_settings.iam_audience,
        },
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
