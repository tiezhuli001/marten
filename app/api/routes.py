from functools import lru_cache

from typing import Any

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request

from app.agents.code_review_agent import ReviewService
from app.agents.main_agent import MainAgentService
from app.agents.ralph import SleepCodingService
from app.channel.feishu import FeishuWebhookService
from app.control.automation import AutomationService
from app.control.gateway import GatewayControlPlaneService
from app.control.session_registry import SessionRegistryService
from app.control.task_registry import TaskRegistryService
from app.control.sleep_coding_worker import SleepCodingWorkerService
from app.control.workflow import GatewayWorkflowService
from app.core.config import get_settings
from app.infra.diagnostics import IntegrationDiagnosticsService
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    ControlTask,
    ControlTaskEvent,
    GatewayMessageRequest,
    GatewayMessageResponse,
    MainAgentIntakeRequest,
    MainAgentIntakeResponse,
    ReviewActionRequest,
    ReviewRun,
    SleepCodingTask,
    SleepCodingWorkerClaim,
    SleepCodingWorkerPollRequest,
    SleepCodingWorkerPollResponse,
)

router = APIRouter()


@lru_cache(maxsize=1)
def get_gateway_control_plane_service() -> GatewayControlPlaneService:
    settings = get_settings()
    return GatewayControlPlaneService(
        settings=settings,
        ledger=get_token_ledger_service(),
        main_agent=get_main_agent_service(),
        sleep_coding=get_sleep_coding_service(),
        sessions=get_session_registry_service(),
    )


@lru_cache(maxsize=1)
def get_feishu_webhook_service() -> FeishuWebhookService:
    return FeishuWebhookService(
        get_settings(),
        get_gateway_workflow_service(),
    )


@lru_cache(maxsize=1)
def get_gateway_workflow_service() -> GatewayWorkflowService:
    settings = get_settings()
    return GatewayWorkflowService(
        settings=settings,
        control_plane=get_gateway_control_plane_service(),
        automation=get_automation_service(),
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
def get_review_service() -> ReviewService:
    return ReviewService()


@lru_cache(maxsize=1)
def get_token_ledger_service() -> TokenLedgerService:
    return TokenLedgerService(get_settings())


@lru_cache(maxsize=1)
def get_task_registry_service() -> TaskRegistryService:
    return TaskRegistryService(get_settings())


@lru_cache(maxsize=1)
def get_session_registry_service():
    return SessionRegistryService(get_settings())


@lru_cache(maxsize=1)
def get_integration_diagnostics_service() -> IntegrationDiagnosticsService:
    return IntegrationDiagnosticsService(get_settings())


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/gateway/message", response_model=GatewayMessageResponse)
def handle_message(
    payload: GatewayMessageRequest,
    control_plane: GatewayControlPlaneService = Depends(get_gateway_control_plane_service),
) -> GatewayMessageResponse:
    return control_plane.run(payload)


@router.post("/webhooks/feishu/events")
async def handle_feishu_events(
    request: Request,
    service: FeishuWebhookService = Depends(get_feishu_webhook_service),
) -> dict[str, Any]:
    try:
        raw_body = await request.body()
        headers = dict(request.headers)
        return await anyio.to_thread.run_sync(service.handle_event, raw_body, headers)
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


@router.get("/tasks/sleep-coding/{task_id}", response_model=SleepCodingTask)
def get_sleep_coding_task(
    task_id: str,
    service: SleepCodingService = Depends(get_sleep_coding_service),
) -> SleepCodingTask:
    try:
        return service.get_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reviews/{review_id}", response_model=ReviewRun)
def get_review_run(
    review_id: str,
    service: ReviewService = Depends(get_review_service),
) -> ReviewRun:
    try:
        return service.get_review(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
