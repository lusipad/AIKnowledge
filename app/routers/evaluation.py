from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.security import require_min_role
from app.schemas import EvaluationRunRequest
from app.services.evaluation import get_evaluation_run, list_evaluation_runs, list_evaluation_scenarios, run_evaluation
from app.settings import load_settings
from app.utils import api_response


router = APIRouter(prefix='/api/v1', tags=['evaluation'])


@router.get('/evaluation/scenarios')
def get_evaluation_scenarios(_: str = Depends(require_min_role('viewer'))):
    return api_response({'items': list_evaluation_scenarios()})


@router.post('/evaluation/run')
def create_evaluation_run(
    payload: EvaluationRunRequest,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('admin')),
):
    try:
        report = run_evaluation(database, load_settings(), payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_response(report)


@router.get('/evaluation/runs')
def get_evaluation_runs(
    limit: int = 20,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    return api_response({'items': list_evaluation_runs(database, limit=limit)})


@router.get('/evaluation/runs/{run_id}')
def get_evaluation_run_detail(
    run_id: str,
    database: Session = Depends(get_db),
    _: str = Depends(require_min_role('viewer')),
):
    report = get_evaluation_run(database, run_id)
    if not report:
        raise HTTPException(status_code=404, detail='evaluation run not found')
    return api_response(report)
