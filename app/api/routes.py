from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.graph.workflow import WorkflowRunner
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    DailyTokenSummary,
    GatewayMessageRequest,
    GatewayMessageResponse,
    ReviewActionRequest,
    ReviewRun,
    ReviewRunRequest,
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    TokenReportResponse,
)
from app.services.review import ReviewService
from app.services.status import StatusService
from app.services.sleep_coding import SleepCodingService

router = APIRouter()


@lru_cache(maxsize=1)
def get_workflow_runner() -> WorkflowRunner:
    return WorkflowRunner()


@lru_cache(maxsize=1)
def get_status_service() -> StatusService:
    return StatusService()


@lru_cache(maxsize=1)
def get_sleep_coding_service() -> SleepCodingService:
    return SleepCodingService()


@lru_cache(maxsize=1)
def get_review_service() -> ReviewService:
    return ReviewService()


@lru_cache(maxsize=1)
def get_token_ledger_service() -> TokenLedgerService:
    return TokenLedgerService(get_settings())


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/gateway/message", response_model=GatewayMessageResponse)
def handle_message(
    payload: GatewayMessageRequest,
    workflow: WorkflowRunner = Depends(get_workflow_runner),
) -> GatewayMessageResponse:
    return workflow.run(payload)


@router.get("/status/current")
def current_status(
    status_service: StatusService = Depends(get_status_service),
) -> dict[str, str]:
    return {"content": status_service.read_current_status()}


@router.post("/tasks/sleep-coding", response_model=SleepCodingTask)
def create_sleep_coding_task(
    payload: SleepCodingTaskRequest,
    service: SleepCodingService = Depends(get_sleep_coding_service),
) -> SleepCodingTask:
    try:
        return service.start_task(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/sleep-coding/{task_id}", response_model=SleepCodingTask)
def get_sleep_coding_task(
    task_id: str,
    service: SleepCodingService = Depends(get_sleep_coding_service),
) -> SleepCodingTask:
    try:
        return service.get_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/sleep-coding/{task_id}/actions", response_model=SleepCodingTask)
def apply_sleep_coding_action(
    task_id: str,
    payload: SleepCodingTaskActionRequest,
    service: SleepCodingService = Depends(get_sleep_coding_service),
) -> SleepCodingTask:
    try:
        return service.apply_action(task_id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews", response_model=ReviewRun)
def create_review_run(
    payload: ReviewRunRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewRun:
    try:
        return service.start_review(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reviews/{review_id}", response_model=ReviewRun)
def get_review_run(
    review_id: str,
    service: ReviewService = Depends(get_review_service),
) -> ReviewRun:
    try:
        return service.get_review(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/actions", response_model=ReviewRun)
def apply_review_action(
    review_id: str,
    payload: ReviewActionRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewRun:
    try:
        return service.apply_action(review_id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/sleep-coding/{task_id}/review", response_model=ReviewRun)
def trigger_sleep_coding_review(
    task_id: str,
    service: ReviewService = Depends(get_review_service),
) -> ReviewRun:
    try:
        return service.trigger_for_task(task_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reports/tokens", response_model=TokenReportResponse)
def get_token_report(
    window: str,
    service: TokenLedgerService = Depends(get_token_ledger_service),
) -> TokenReportResponse:
    try:
        return service.get_window_report(window)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reports/tokens/daily/{summary_date}", response_model=DailyTokenSummary)
def get_daily_token_summary(
    summary_date: str,
    service: TokenLedgerService = Depends(get_token_ledger_service),
) -> DailyTokenSummary:
    try:
        return service.get_daily_summary(summary_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reports/tokens/daily/generate", response_model=DailyTokenSummary)
def generate_daily_token_summary(
    date: str | None = None,
    service: TokenLedgerService = Depends(get_token_ledger_service),
) -> DailyTokenSummary:
    try:
        return (
            service.generate_daily_summary(date)
            if date
            else service.generate_yesterday_summary()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
