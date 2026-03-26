from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.main import create_app


@asynccontextmanager
async def noop_lifespan(_: FastAPI):
    yield


def build_test_app() -> FastAPI:
    return create_app(lifespan_manager=noop_lifespan)
