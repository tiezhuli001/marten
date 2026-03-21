from __future__ import annotations

from dataclasses import dataclass

from app.control.automation import AutomationService
from app.control.gateway import GatewayControlPlaneService
from app.core.config import Settings, get_settings
from app.models.schemas import GatewayMessageRequest, GatewayMessageResponse


@dataclass(frozen=True)
class GatewayWorkflowResult:
    gateway_response: GatewayMessageResponse
    follow_up: dict[str, object]


class GatewayWorkflowService:
    def __init__(
        self,
        settings: Settings | None = None,
        control_plane: GatewayControlPlaneService | None = None,
        automation: AutomationService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.control_plane = control_plane or GatewayControlPlaneService(self.settings)
        self.automation = automation or AutomationService(self.settings)

    def run(self, payload: GatewayMessageRequest) -> GatewayWorkflowResult:
        gateway_response = self.control_plane.run(payload)
        follow_up = self.automation.continue_gateway_workflow(
            intent=gateway_response.intent,
            task_id=gateway_response.task_id,
        )
        return GatewayWorkflowResult(
            gateway_response=gateway_response,
            follow_up=follow_up,
        )
