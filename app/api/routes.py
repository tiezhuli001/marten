from functools import lru_cache

from fastapi import APIRouter, Depends

from app.graph.workflow import WorkflowRunner
from app.models.schemas import GatewayMessageRequest, GatewayMessageResponse
from app.services.status import StatusService

router = APIRouter()


@lru_cache(maxsize=1)
def get_workflow_runner() -> WorkflowRunner:
    return WorkflowRunner()


@lru_cache(maxsize=1)
def get_status_service() -> StatusService:
    return StatusService()


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
