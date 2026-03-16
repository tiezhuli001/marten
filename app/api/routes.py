from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.graph.workflow import WorkflowRunner
from app.models.schemas import (
    GatewayMessageRequest,
    GatewayMessageResponse,
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
)
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
