from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, SessionLocal, engine
from app.routers.audit import router as audit_router
from app.routers.config import router as config_router
from app.routers.context import router as context_router
from app.routers.feedback import router as feedback_router
from app.routers.knowledge import router as knowledge_router
from app.routers.llm import router as llm_router
from app.routers.retrieval import router as retrieval_router
from app.routers.sessions import router as sessions_router
from app.security import ApiKeyMiddleware
from app.services.bootstrap import seed_default_profiles
from app.services.health import database_healthcheck
from app.settings import load_settings


settings = load_settings()


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

app.include_router(sessions_router)
app.include_router(context_router)
app.include_router(knowledge_router)
app.include_router(llm_router)
app.include_router(retrieval_router)
app.include_router(config_router)
app.include_router(feedback_router)
app.include_router(audit_router)


@app.get('/')
def root():
    return {
        'service': 'ai-coding-knowledge-memory-mvp',
        'status': 'ok',
        'docs': '/docs',
        'version': settings.app_version,
        'env': settings.env,
        'auth_enabled': settings.api_key_enabled,
        'vector_backend': settings.vector_backend,
        'llm_configured': settings.llm_configured,
    }


@app.get('/healthz')
def healthz():
    db_ok, db_detail = database_healthcheck()
    return {
        'status': 'ok' if db_ok else 'degraded',
        'database': {'ok': db_ok, 'detail': db_detail},
        'vector_backend': settings.vector_backend,
        'auth_enabled': settings.api_key_enabled,
        'llm': {
            'configured': settings.llm_configured,
            'model': settings.llm_model,
            'base_url': settings.llm_base_url,
        },
        'version': settings.app_version,
    }
