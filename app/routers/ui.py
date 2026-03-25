from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse


router = APIRouter(include_in_schema=False)

STATIC_ROOT = Path(__file__).resolve().parents[1] / 'static'
CONSOLE_ROOT = STATIC_ROOT / 'console'


@router.get('/console')
@router.get('/console/')
def console() -> FileResponse:
    return FileResponse(CONSOLE_ROOT / 'index.html')


@router.get('/favicon.ico')
def favicon() -> RedirectResponse:
    return RedirectResponse(url='/static/console/assets/favicon.svg', status_code=307)
