from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from uuid import uuid4

from app.agents.main_agent import MainAgentService
from app.agents.ralph import SleepCodingService
from app.channel.endpoints import ChannelEndpointRegistry
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
from app.control.session_registry import (
    SessionRegistryService,
    build_user_session_external_ref,
)
from app.control.task_registry import TaskRegistryService


@dataclass(frozen=True)
class _GatewayChainContext:
    chain_request_id: str
    linked_user_session_id: str | None = None
    parent_task_id: str | None = None


class GatewayControlPlaneService:
    _LANE_GUARD = threading.Lock()
    _LANE_LOCKS: dict[str, threading.Lock] = {}
    _DEFAULT_EXECUTION_LANE = "self_host:default"

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
        self.endpoints = ChannelEndpointRegistry(self.settings)

    def run(self, payload: GatewayMessageRequest) -> GatewayMessageResponse:
        user_session_ref = build_user_session_external_ref(
            source=payload.source,
            user_id=payload.user_id,
            session_key=payload.session_key,
        )
        dedupe_key = self._build_dedupe_key(payload, user_session_ref)
        if dedupe_key:
            cached = self.sessions.find_inbound_receipt(dedupe_key)
            if cached is not None:
                return GatewayMessageResponse.model_validate(cached)
        lane_lock = self._get_lane_lock(user_session_ref)
        with lane_lock:
            if dedupe_key:
                cached = self.sessions.find_inbound_receipt(dedupe_key)
                if cached is not None:
                    return GatewayMessageResponse.model_validate(cached)
            request_id = payload.request_id or str(uuid4())
            run_id = str(uuid4())
            source_endpoint_id = self.endpoints.resolve_endpoint_id(
                endpoint_id=payload.endpoint_id,
                provider=payload.source,
                external_refs=[user_session_ref, payload.chat_id] if payload.chat_id else [user_session_ref],
            )
            binding = self.endpoints.resolve_binding(source_endpoint_id)
            route = resolve_route(payload.content, endpoint_binding=binding)
            delivery_endpoint_id = self.endpoints.resolve_delivery_endpoint_id(
                source_endpoint_id=source_endpoint_id,
                workflow=route.intent,
            )
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
                source_endpoint_id=source_endpoint_id,
                delivery_endpoint_id=delivery_endpoint_id,
                user_session_ref=user_session_ref,
                linked_user_session_id=chain_context.linked_user_session_id,
                parent_task_id=chain_context.parent_task_id,
            )
            if route.intent == "stats_query":
                usage, message, task_id, workflow_state, active_task_id = self._handle_stats_query(payload)
            else:
                usage, message, task_id, workflow_state, active_task_id = self._handle_route(
                    route=route,
                    payload=payload,
                    request_id=request_id,
                    run_id=run_id,
                    chain_request_id=chain_context.chain_request_id,
                    source_endpoint_id=source_endpoint_id,
                    delivery_endpoint_id=delivery_endpoint_id,
                )
            self._record_routing_failure(
                task_id=task_id,
                route=route,
                source_endpoint_id=source_endpoint_id,
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
            response = GatewayMessageResponse(
                request_id=request_id,
                chain_request_id=chain_context.chain_request_id,
                intent=route.intent,
                message=message,
                token_usage=recorded,
                task_id=task_id,
                run_session_id=run_session.session_id,
                source_endpoint_id=source_endpoint_id,
                delivery_endpoint_id=delivery_endpoint_id,
                workflow_state=workflow_state,
                active_task_id=active_task_id,
            )
            self._record_session_turn(
                run_session=run_session,
                response=response,
            )
            if dedupe_key:
                self.sessions.record_inbound_receipt(dedupe_key, response.model_dump(mode="json"))
            return response

    @classmethod
    def _get_lane_lock(cls, lane_key: str) -> threading.Lock:
        with cls._LANE_GUARD:
            if lane_key not in cls._LANE_LOCKS:
                cls._LANE_LOCKS[lane_key] = threading.Lock()
            return cls._LANE_LOCKS[lane_key]

    def _build_dedupe_key(self, payload: GatewayMessageRequest, user_session_ref: str) -> str | None:
        if payload.message_id:
            return f"{payload.source}:{user_session_ref}:message:{payload.message_id}"
        if payload.request_id:
            return f"{payload.source}:{user_session_ref}:request:{payload.request_id}"
        return None

    def _record_routing_failure(
        self,
        *,
        task_id: str | None,
        route: GatewayRoute,
        source_endpoint_id: str,
    ) -> None:
        if task_id is None:
            return
        if route.routing_failure_reason is None or route.requested_agent is None:
            return
        self.tasks.append_event(
            task_id,
            "routing_failure",
            {
                "requested_agent": route.requested_agent,
                "resolved_agent": route.target_agent,
                "reason": route.routing_failure_reason,
                "source_endpoint_id": source_endpoint_id,
            },
        )

    def _record_session_turn(
        self,
        *,
        run_session,
        response: GatewayMessageResponse,
    ) -> None:  # noqa: ANN001
        self.sessions.record_session_turn(
            run_session.session_id,
            request_id=response.request_id,
            chain_request_id=response.chain_request_id,
            intent=response.intent,
            workflow_state=response.workflow_state,
            task_id=response.task_id,
            source_endpoint_id=response.source_endpoint_id or "default",
            delivery_endpoint_id=response.delivery_endpoint_id or "default",
            run_session_id=response.run_session_id,
        )
        parent_session_id = getattr(run_session, "parent_session_id", None)
        if isinstance(parent_session_id, str) and parent_session_id.strip():
            self.sessions.record_session_turn(
                parent_session_id,
                request_id=response.request_id,
                chain_request_id=response.chain_request_id,
                intent=response.intent,
                workflow_state=response.workflow_state,
                task_id=response.task_id,
                source_endpoint_id=response.source_endpoint_id or "default",
                delivery_endpoint_id=response.delivery_endpoint_id or "default",
                run_session_id=response.run_session_id,
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
        source_endpoint_id: str,
        delivery_endpoint_id: str,
        user_session_ref: str,
        linked_user_session_id: str | None = None,
        parent_task_id: str | None = None,
    ):
        user_session = (
            self.sessions.get_session(linked_user_session_id)
            if linked_user_session_id
            else self.sessions.get_or_create_session(
                session_type="user_session",
                external_ref=user_session_ref,
                user_id=user_id,
                source=source,
                payload={
                    "source_endpoint_id": source_endpoint_id,
                    "delivery_endpoint_id": delivery_endpoint_id,
                },
            )
        )
        self.sessions.update_session_payload(
            user_session.session_id,
            {
                "source_endpoint_id": source_endpoint_id,
                "delivery_endpoint_id": delivery_endpoint_id,
                "user_session_ref": user_session_ref,
            },
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
                "active_workflow": intent,
                "direct_mention": direct_mention,
                "chain_request_id": chain_request_id,
                "source_endpoint_id": source_endpoint_id,
                "delivery_endpoint_id": delivery_endpoint_id,
                "session_lane_key": user_session_ref,
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
        source_endpoint_id: str,
        delivery_endpoint_id: str,
    ) -> tuple[TokenUsage, str, str | None, str, str | None]:
        if route.target_agent == "ralph":
            return self._handle_sleep_coding(
                payload,
                chain_request_id,
                source_endpoint_id,
                delivery_endpoint_id,
            )
        return self._handle_general(
            payload,
            request_id,
            run_id,
            source_endpoint_id,
            delivery_endpoint_id,
        )

    def _handle_general(
        self,
        payload: GatewayMessageRequest,
        request_id: str,
        run_id: str,
        source_endpoint_id: str,
        delivery_endpoint_id: str,
    ) -> tuple[TokenUsage, str, str | None, str, str | None]:
        intake = self.main_agent.intake(
            MainAgentIntakeRequest(
                user_id=payload.user_id,
                content=payload.content,
                source=payload.source,
                request_id=request_id,
                run_id=run_id,
                persist_usage=False,
                source_endpoint_id=source_endpoint_id,
                delivery_endpoint_id=delivery_endpoint_id,
                session_key=payload.session_key,
            )
        )
        if intake.mode == "chat":
            return intake.token_usage, intake.message, None, "completed", None
        assert intake.control_task_id is not None
        lane_decision = self.sessions.acquire_execution_lane(
            intake.control_task_id,
            lane_key=self._DEFAULT_EXECUTION_LANE,
        )
        self.tasks.update_task(
            intake.control_task_id,
            payload_patch={
                "queue_status": "queued" if lane_decision.disposition == "queued" else "running",
                "active_task_id": lane_decision.snapshot.active_task_id,
                "queued_task_ids": lane_decision.snapshot.queued_task_ids,
            },
        )
        self.tasks.append_event(
            intake.control_task_id,
            f"single_flight.{lane_decision.disposition}",
            {
                "active_task_id": lane_decision.snapshot.active_task_id,
                "queued_task_ids": lane_decision.snapshot.queued_task_ids,
            },
        )
        issue_url = intake.issue.html_url if intake.issue is not None else None
        message = f"{intake.message}. Issue URL: {issue_url or 'n/a'}."
        if lane_decision.disposition == "queued":
            message = (
                f"{message} 当前主任务仍在执行，新的请求已排队。"
            )
        return (
            intake.token_usage,
            message,
            intake.control_task_id,
            "queued" if lane_decision.disposition == "queued" else "accepted",
            lane_decision.snapshot.active_task_id,
        )

    def _handle_stats_query(
        self,
        payload: GatewayMessageRequest,
    ) -> tuple[TokenUsage, str, str | None, str, str | None]:
        summary = self.ledger.get_usage_summary(query=payload.content)
        return TokenUsage(step_name="stats_query_handler"), summary, None, "completed", None

    def _handle_sleep_coding(
        self,
        payload: GatewayMessageRequest,
        request_id: str,
        source_endpoint_id: str,
        delivery_endpoint_id: str,
    ) -> tuple[TokenUsage, str, str | None, str, str | None]:
        lane_snapshot = self.sessions.get_execution_lane(self._DEFAULT_EXECUTION_LANE)
        if lane_snapshot.active_task_id:
            message = (
                "Sleep coding queue is busy. Wait for the current active task to finish before starting another direct Ralph task."
            )
            return TokenUsage(step_name="sleep_coding_handler"), message, None, "running", lane_snapshot.active_task_id
        issue_number = self._extract_issue_number(payload.content)
        if issue_number is None:
            return (
                TokenUsage(step_name="sleep_coding_handler"),
                "Sleep coding intent recognized. Provide an issue number to continue.",
                None,
                "completed",
                None,
            )

        task = self.sleep_coding.start_task(
            SleepCodingTaskRequest(
                issue_number=issue_number,
                request_id=request_id,
                notify_plan_ready=True,
                source_endpoint_id=source_endpoint_id,
                delivery_endpoint_id=delivery_endpoint_id,
            )
        )
        if task.control_task_id:
            lane_decision = self.sessions.acquire_execution_lane(
                task.control_task_id,
                lane_key=self._DEFAULT_EXECUTION_LANE,
            )
            self.tasks.update_task(
                task.control_task_id,
                payload_patch={
                    "queue_status": "running",
                    "active_task_id": lane_decision.snapshot.active_task_id,
                    "queued_task_ids": lane_decision.snapshot.queued_task_ids,
                },
            )
        message = (
            f"Sleep coding task {task.task_id} is ready for review. "
            f"Status={task.status}, branch={task.head_branch}."
        )
        return TokenUsage(step_name="sleep_coding_handler"), message, task.task_id, "accepted", task.control_task_id

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
