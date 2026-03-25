from fastapi import APIRouter, Depends

from app.security import require_min_role
from app.schemas import LlmVerifyRequest
from app.services.llm_validation import verify_llm_connection
from app.settings import load_settings
from app.utils import api_response


router = APIRouter(prefix='/api/v1', tags=['llm'])


@router.get('/llm/config')
def get_llm_config(_: str = Depends(require_min_role('viewer'))):
    settings = load_settings()
    return api_response(
        {
            'configured': settings.llm_configured,
            'base_url': settings.llm_base_url,
            'chat_path': settings.llm_chat_path,
            'model': settings.llm_model,
            'timeout_sec': settings.llm_timeout_sec,
        }
    )


@router.post('/llm/verify')
def verify_llm(payload: LlmVerifyRequest, _: str = Depends(require_min_role('admin'))):
    settings = load_settings()
    result = verify_llm_connection(settings, prompt=payload.prompt, max_tokens=payload.max_tokens)
    return api_response(result.to_dict())
