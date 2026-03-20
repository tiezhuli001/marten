from __future__ import annotations

import re
from dataclasses import dataclass
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
from app.control.routing import GatewayRoute, resolve_route
from app.control.session_registry import SessionRegistryService
from app.control.task_registry import TaskRegistryService


@dataclass(frozen=True)
class _GatewayChainContext:
    chain_request_id: str
    linked_user_session_id: str | None = None
    parent_task_id: str | None = None


class GatewayControlPlaneService:
    def __init__(
        self,
        settings: Settings | None = None,
        ledger: TokenLedgerService | None = None,
        main_agent: MainAgentService | None = None,
        sleep_coding: SleepCodingService | None = None,
        sessions: SessionRegistryService | None = None,
        tasks: TaskRegistryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ledger = ledger or TokenLedgerService(self.settings)
        self.main_agent = main_agent or MainAgentService(self.settings)
        self.sleep_coding = sleep_coding or SleepCodingService(settings=self.settings, ledger=self.ledger)
        self.sessions = sessions or SessionRegistryService(self.settings)
        self.tasks = tasks or TaskRegistryService(self.settings)

    def run(self, payload: GatewayMessageRequest) -> GatewayMessageResponse:
        request_id = payload.request_id or str(uuid4())
        run_id = str(uuid4())
        route = resolve_route(payload.content)
        chain_context = self._resolve_chain_context(
            payload=payload,
            request_id=request_id,
            route=route,
        )
        run_session = self._ensure_sessions(
            request_id=request_id,
            chain_request_id=chain_context.chain_request_id,
            user_id=payload.user_id,
            source=payload.source,
            intent=route.intent,
            content=payload.content,
            target_agent=route.target_agent,
            direct_mention=route.direct_mention,
            linked_user_session_id=chain_context.linked_user_session_id,
            parent_task_id=chain_context.parent_task_id,
        )
        if route.intent == "stats_query":
            usage, message, task_id = self._handle_stats_query(payload)
        else:
            usage, message, task_id = self._handle_route(
                route=route,
                payload=payload,
                request_id=request_id,
                run_id=run_id,
                chain_request_id=chain_context.chain_request_id,
            )
        recorded = self.ledger.record_request(
            request_id=request_id,
            run_id=run_id,
            user_id=payload.user_id,
            source=payload.source,
            intent=route.intent,
            content=payload.content,
            usage=usage,
        )
        return GatewayMessageResponse(
            request_id=request_id,
            chain_request_id=chain_context.chain_request_id,
            intent=route.intent,
            message=message,
            token_usage=recorded,
            task_id=task_id,
            run_session_id=run_session.session_id,
        )

    def _ensure_sessions(
        self,
        *,
        request_id: str,
        chain_request_id: str,
        user_id: str,
        source: str,
        intent: str,
        content: str,
        target_agent: str,
        direct_mention: bool,
        linked_user_session_id: str | None = None,
        parent_task_id: str | None = None,
    ):
        user_session = self.sessions.get_or_create_session(
            session_type="user_session",
            external_ref=f"{source}:{user_id}",
            user_id=user_id,
            source=source,
        )
        self.sessions.set_active_agent(user_session.session_id, target_agent)
        return self.sessions.get_or_create_session(
            session_type="run_session",
            external_ref=f"gateway:{request_id}",
            user_id=user_id,
            source=source,
            parent_session_id=user_session.session_id,
            payload={
                "intent": intent,
                "content": content,
                "target_agent": target_agent,
                "direct_mention": direct_mention,
                "chain_request_id": chain_request_id,
                "linked_user_session_id": linked_user_session_id,
                "parent_task_id": parent_task_id,
            },
        )

    def _resolve_chain_context(
        self,
        *,
        payload: GatewayMessageRequest,
        request_id: str,
        route: GatewayRoute,
    ) -> _GatewayChainContext:
        if payload.chain_request_id:
            return _GatewayChainContext(chain_request_id=payload.chain_request_id)
        if route.intent != "sleep_coding":
            return _GatewayChainContext(chain_request_id=request_id)
        issue_number = self._extract_issue_number(payload.content)
        if issue_number is None:
            return _GatewayChainContext(chain_request_id=request_id)
        repo = self.settings.resolved_github_repository
        if not repo:
            return _GatewayChainContext(chain_request_id=request_id)
        parent_task = self.tasks.find_parent_for_issue(repo, issue_number)
        if parent_task is None:
            return _GatewayChainContext(chain_request_id=request_id)
        inherited_request_id = parent_task.payload.get("request_id")
        chain_request_id = (
            inherited_request_id
            if isinstance(inherited_request_id, str) and inherited_request_id.strip()
            else request_id
        )
        linked_user_session_id = parent_task.payload.get("user_session_id")
        return _GatewayChainContext(
            chain_request_id=chain_request_id,
            linked_user_session_id=(
                linked_user_session_id
                if isinstance(linked_user_session_id, str) and linked_user_session_id.strip()
                else None
            ),
            parent_task_id=parent_task.task_id,
        )

    def _handle_route(
        self,
        *,
        route: GatewayRoute,
        payload: GatewayMessageRequest,
        request_id: str,
        run_id: str,
        chain_request_id: str,
    ) -> tuple[TokenUsage, str, str | None]:
        if route.target_agent == "ralph":
            return self._handle_sleep_coding(payload, chain_request_id)
        return self._handle_general(payload, request_id, run_id)

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
                "Sleep coding intent recognized. Provide an issue number to continue.",
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
