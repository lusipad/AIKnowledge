from __future__ import annotations

import os
from dataclasses import dataclass


ALLOWED_VECTOR_BACKENDS = {'simple', 'keyword', 'simple-keyword', 'pgvector', 'postgres'}


@dataclass(frozen=True)
class AppSettings:
    app_name: str
    app_version: str
    db_url: str
    vector_backend: str
    api_key: str | None
    env: str

    @property
    def api_key_enabled(self) -> bool:
        return bool(self.api_key)



def load_settings() -> AppSettings:
    vector_backend = os.getenv('AICODING_VECTOR_BACKEND', 'simple').lower()
    if vector_backend not in ALLOWED_VECTOR_BACKENDS:
        raise ValueError(f'Unsupported vector backend: {vector_backend}')

    return AppSettings(
        app_name='AI Coding Knowledge & Memory MVP',
        app_version='0.3.0',
        db_url=os.getenv('AICODING_DB_URL', 'sqlite:///./aicoding_mvp.db'),
        vector_backend=vector_backend,
        api_key=os.getenv('AICODING_API_KEY') or None,
        env=os.getenv('AICODING_ENV', 'dev'),
    )
