from __future__ import annotations

import re
from uuid import uuid4

from app.agents.main_agent import MainAgentService
from app.agents.ralph import SleepCodingService
from app.core.config import Settings, get_settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GatewayMessageRequest,
    GatewayMessageResponse,
    MainAgentIntakeRequest,
    SleepCodingTaskRequest,
    TokenUsage,
)
from app.services.session_registry import SessionRegistryService
from app.control.routing import classify_intent


class GatewayControlPlaneService:
    def __init__(
        self,
        settings: Settings | None = None,
        ledger: TokenLedgerService | None = None,
        main_agent: MainAgentService | None = None,
        sleep_coding: SleepCodingService | None = None,
        sessions: SessionRegistryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ledger = ledger or TokenLedgerService(self.settings)
        self.main_agent = main_agent or MainAgentService(self.settings)
        self.sleep_coding = sleep_coding or SleepCodingService(settings=self.settings, ledger=self.ledger)
        self.sessions = sessions or SessionRegistryService(self.settings)

    def run(self, payload: GatewayMessageRequest) -> GatewayMessageResponse:
        request_id = str(uuid4())
        run_id = str(uuid4())
        intent = classify_intent(payload.content)
        self._ensure_sessions(
            request_id=request_id,
            user_id=payload.user_id,
            source=payload.source,
            intent=intent,
            content=payload.content,
        )
        if intent == "general":
            usage, message, task_id = self._handle_general(payload, request_id, run_id)
        elif intent == "stats_query":
            usage, message, task_id = self._handle_stats_query(payload)
        else:
            usage, message, task_id = self._handle_sleep_coding(payload, request_id)
        recorded = self.ledger.record_request(
            request_id=request_id,
            run_id=run_id,
            user_id=payload.user_id,
            source=payload.source,
            intent=intent,
            content=payload.content,
            usage=usage,
        )
        return GatewayMessageResponse(
            request_id=request_id,
            intent=intent,
            message=message,
            token_usage=recorded,
            task_id=task_id,
        )

    def _ensure_sessions(
        self,
        *,
        request_id: str,
        user_id: str,
        source: str,
        intent: str,
        content: str,
    ) -> None:
        user_session = self.sessions.get_or_create_session(
            session_type="user_session",
            external_ref=f"{source}:{user_id}",
            user_id=user_id,
            source=source,
        )
        self.sessions.get_or_create_session(
            session_type="run_session",
            external_ref=f"gateway:{request_id}",
            user_id=user_id,
            source=source,
            parent_session_id=user_session.session_id,
            payload={"intent": intent, "content": content},
        )

    def _handle_general(
        self,
        payload: GatewayMessageRequest,
        request_id: str,
        run_id: str,
    ) -> tuple[TokenUsage, str, str | None]:
        intake = self.main_agent.intake(
            MainAgentIntakeRequest(
                user_id=payload.user_id,
                content=payload.content,
                source=payload.source,
                request_id=request_id,
                run_id=run_id,
                persist_usage=False,
            )
        )
        message = f"{intake.message}. Issue URL: {intake.issue.html_url or 'n/a'}."
        return intake.token_usage, message, intake.control_task_id

    def _handle_stats_query(
        self,
        payload: GatewayMessageRequest,
    ) -> tuple[TokenUsage, str, str | None]:
        summary = self.ledger.get_usage_summary(query=payload.content)
        return TokenUsage(step_name="stats_query_handler"), summary, None

    def _handle_sleep_coding(
        self,
        payload: GatewayMessageRequest,
        request_id: str,
    ) -> tuple[TokenUsage, str, str | None]:
        issue_number = self._extract_issue_number(payload.content)
        if issue_number is None:
            return (
                TokenUsage(step_name="sleep_coding_handler"),
                "Sleep coding intent recognized. Provide an issue number or call POST /tasks/sleep-coding directly.",
                None,
            )

        task = self.sleep_coding.start_task(
            SleepCodingTaskRequest(
                issue_number=issue_number,
                request_id=request_id,
                notify_plan_ready=True,
            )
        )
        message = (
            f"Sleep coding task {task.task_id} is ready for review. "
            f"Status={task.status}, branch={task.head_branch}."
        )
        return TokenUsage(step_name="sleep_coding_handler"), message, task.task_id

    def _extract_issue_number(self, content: str) -> int | None:
        patterns = (
            r"(?:issue|Issue)\s*#?(\d+)",
            r"#(\d+)",
        )
        for pattern in patterns:
            match = re.search(pattern, content)
            if match is not None:
                return int(match.group(1))
        return None
