from functools import lru_cache

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import get_settings
from app.graph.workflow import WorkflowRunner
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    ControlTask,
    ControlTaskEvent,
    DailyTokenSummary,
    GatewayMessageRequest,
    GatewayMessageResponse,
    MainAgentIntakeRequest,
    MainAgentIntakeResponse,
    ReviewActionRequest,
    ReviewRun,
    ReviewRunRequest,
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    SleepCodingWorkerClaim,
    SleepCodingWorkerPollRequest,
    SleepCodingWorkerPollResponse,
    TokenReportResponse,
)
from app.services.automation import AutomationService
from app.services.diagnostics import IntegrationDiagnosticsService
from app.services.review import ReviewService
from app.services.feishu import FeishuWebhookService
from app.services.main_agent import MainAgentService
from app.services.scheduler import WorkerSchedulerService
from app.services.sleep_coding_worker import SleepCodingWorkerService
from app.services.status import StatusService
from app.services.sleep_coding import SleepCodingService
from app.services.task_registry import TaskRegistryService

router = APIRouter()


@lru_cache(maxsize=1)
def get_workflow_runner() -> WorkflowRunner:
    return WorkflowRunner()


@lru_cache(maxsize=1)
def get_status_service() -> StatusService:
    return StatusService()


@lru_cache(maxsize=1)
def get_feishu_webhook_service() -> FeishuWebhookService:
    return FeishuWebhookService(
        get_settings(),
        get_workflow_runner(),
        get_automation_service(),
    )


@lru_cache(maxsize=1)
def get_main_agent_service() -> MainAgentService:
    return MainAgentService(get_settings())


@lru_cache(maxsize=1)
def get_sleep_coding_service() -> SleepCodingService:
    return SleepCodingService()


@lru_cache(maxsize=1)
def get_automation_service() -> AutomationService:
    settings = get_settings()
    sleep_coding = get_sleep_coding_service()
    review = ReviewService(settings=settings, sleep_coding=sleep_coding)
    worker = SleepCodingWorkerService(settings=settings, sleep_coding=sleep_coding)
    return AutomationService(
        settings=settings,
        sleep_coding=sleep_coding,
        review=review,
        worker=worker,
    )


@lru_cache(maxsize=1)
def get_sleep_coding_worker_service() -> SleepCodingWorkerService:
    return SleepCodingWorkerService(get_settings())


@lru_cache(maxsize=1)
def get_worker_scheduler_service() -> WorkerSchedulerService:
    return WorkerSchedulerService(get_settings(), get_automation_service())


@lru_cache(maxsize=1)
def get_review_service() -> ReviewService:
    return ReviewService()


@lru_cache(maxsize=1)
def get_token_ledger_service() -> TokenLedgerService:
    return TokenLedgerService(get_settings())


@lru_cache(maxsize=1)
def get_task_registry_service() -> TaskRegistryService:
    return TaskRegistryService(get_settings())


@lru_cache(maxsize=1)
def get_integration_diagnostics_service() -> IntegrationDiagnosticsService:
    return IntegrationDiagnosticsService(get_settings())


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/gateway/message", response_model=GatewayMessageResponse)
def handle_message(
    payload: GatewayMessageRequest,
    workflow: WorkflowRunner = Depends(get_workflow_runner),
) -> GatewayMessageResponse:
    return workflow.run(payload)


@router.post("/webhooks/feishu/events")
async def handle_feishu_events(
    request: Request,
    service: FeishuWebhookService = Depends(get_feishu_webhook_service),
) -> dict[str, Any]:
    try:
        return service.handle_event(await request.body(), request.headers)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/main-agent/intake", response_model=MainAgentIntakeResponse)
def intake_main_agent(
    payload: MainAgentIntakeRequest,
    service: MainAgentService = Depends(get_main_agent_service),
) -> MainAgentIntakeResponse:
    try:
        return service.intake(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status/current")
def current_status(
    status_service: StatusService = Depends(get_status_service),
) -> dict[str, str]:
    return {"content": status_service.read_current_status()}


@router.get("/diagnostics/integrations")
def integration_diagnostics(
    service: IntegrationDiagnosticsService = Depends(get_integration_diagnostics_service),
) -> dict[str, object]:
    return service.get_report()


@router.get("/control/tasks/{task_id}", response_model=ControlTask)
def get_control_task(
    task_id: str,
    service: TaskRegistryService = Depends(get_task_registry_service),
) -> ControlTask:
    try:
        return service.get_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/control/tasks/{task_id}/events", response_model=list[ControlTaskEvent])
def list_control_task_events(
    task_id: str,
    service: TaskRegistryService = Depends(get_task_registry_service),
) -> list[ControlTaskEvent]:
    try:
        service.get_task(task_id)
        return service.list_events(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@router.post("/workers/sleep-coding/poll", response_model=SleepCodingWorkerPollResponse)
def poll_sleep_coding_worker(
    payload: SleepCodingWorkerPollRequest,
    service: AutomationService = Depends(get_automation_service),
) -> SleepCodingWorkerPollResponse:
    try:
        return service.process_worker_poll_async(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workers/sleep-coding/claims", response_model=list[SleepCodingWorkerClaim])
def list_sleep_coding_claims(
    repo: str | None = None,
    service: SleepCodingWorkerService = Depends(get_sleep_coding_worker_service),
) -> list[SleepCodingWorkerClaim]:
    try:
        return service.list_claims(repo=repo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workers/sleep-coding/run-once")
def run_sleep_coding_scheduler_once(
    service: WorkerSchedulerService = Depends(get_worker_scheduler_service),
) -> dict[str, str]:
    service.run_once()
    return {"status": "ok"}


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
    service: AutomationService = Depends(get_automation_service),
) -> SleepCodingTask:
    try:
        return service.handle_sleep_coding_action_async(task_id, payload.action)
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
