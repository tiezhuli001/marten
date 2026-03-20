from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Mapping

from app.control.gateway import GatewayControlPlaneService
from app.core.config import Settings
from app.models.schemas import SleepCodingWorkerPollRequest
from app.models.schemas import GatewayMessageRequest, GatewayMessageResponse
from app.services.automation import AutomationService


@dataclass(frozen=True)
class FeishuInboundMessage:
    user_id: str
    chat_id: str | None
    message_id: str | None
    content: str


class FeishuWebhookService:
    def __init__(
        self,
        settings: Settings,
        control_plane: GatewayControlPlaneService | None = None,
        automation: AutomationService | None = None,
    ) -> None:
        self.settings = settings
        self.control_plane = control_plane or GatewayControlPlaneService(settings)
        self.automation = automation or AutomationService(settings)

    def handle_event(
        self,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> dict[str, object]:
        payload = json.loads(raw_body.decode("utf-8"))
        self._validate_request(raw_body=raw_body, headers=headers, payload=payload)

        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            if not isinstance(challenge, str) or not challenge:
                raise ValueError("Feishu url_verification payload is missing challenge")
            return {"challenge": challenge}

        event_type = self._extract_event_type(payload)
        if event_type != "im.message.receive_v1":
            return {"code": 0, "msg": "ignored", "event_type": event_type}

        message = self._normalize_message_event(payload)
        workflow_response = self.control_plane.run(
            GatewayMessageRequest(
                user_id=message.user_id,
                content=message.content,
                source="feishu",
            )
        )
        follow_up = self._continue_workflow(workflow_response)
        return self._build_ack_response(event_type, message, workflow_response, follow_up)

    def _validate_request(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        payload: dict[str, object],
    ) -> None:
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        is_url_verification = payload.get("type") == "url_verification"
        if self.settings.feishu_verification_token:
            token = payload.get("token")
            if token != self.settings.feishu_verification_token:
                raise PermissionError("Invalid Feishu verification token")
        if is_url_verification:
            return
        if self.settings.feishu_encrypt_key:
            timestamp = normalized_headers.get("x-lark-request-timestamp")
            nonce = normalized_headers.get("x-lark-request-nonce")
            signature = normalized_headers.get("x-lark-signature")
            if not timestamp or not nonce or not signature:
                raise PermissionError("Missing Feishu signature headers")
            expected_signature = self._build_signature(
                timestamp=timestamp,
                nonce=nonce,
                body=raw_body,
            )
            if not hmac.compare_digest(signature, expected_signature):
                raise PermissionError("Invalid Feishu signature")

    def _build_signature(self, *, timestamp: str, nonce: str, body: bytes) -> str:
        signature_source = f"{timestamp}{nonce}{self.settings.feishu_encrypt_key}".encode(
            "utf-8"
        ) + body
        return hashlib.sha256(signature_source).hexdigest()

    def _extract_event_type(self, payload: dict[str, object]) -> str:
        header = payload.get("header")
        if isinstance(header, dict):
            event_type = header.get("event_type")
            if isinstance(event_type, str) and event_type:
                return event_type
        return "unknown"

    def _normalize_message_event(
        self,
        payload: dict[str, object],
    ) -> FeishuInboundMessage:
        event = payload.get("event")
        if not isinstance(event, dict):
            raise ValueError("Feishu event payload is missing event body")
        message = event.get("message")
        if not isinstance(message, dict):
            raise ValueError("Feishu event payload is missing message body")
        if message.get("message_type") not in {None, "text"}:
            raise ValueError("Unsupported Feishu message_type")
        sender = event.get("sender")
        if not isinstance(sender, dict):
            raise ValueError("Feishu event payload is missing sender body")
        sender_id = sender.get("sender_id")
        if not isinstance(sender_id, dict):
            raise ValueError("Feishu sender_id is missing")
        external_user_id = next(
            (
                value
                for key in ("open_id", "user_id", "union_id")
                if isinstance((value := sender_id.get(key)), str) and value
            ),
            None,
        )
        if external_user_id is None:
            raise ValueError("Feishu sender does not include a supported user identifier")
        content = self._extract_text_content(message.get("content"))
        if not content:
            raise ValueError("Feishu text message content is empty")
        return FeishuInboundMessage(
            user_id=f"feishu:{external_user_id}",
            chat_id=message.get("chat_id") if isinstance(message.get("chat_id"), str) else None,
            message_id=message.get("message_id") if isinstance(message.get("message_id"), str) else None,
            content=content,
        )

    def _extract_text_content(self, raw_content: object) -> str:
        if isinstance(raw_content, str):
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict):
                for key in ("text", "content"):
                    value = parsed.get(key)
                    if isinstance(value, str):
                        return value.strip()
        raise ValueError("Unsupported Feishu message content payload")

    def _build_ack_response(
        self,
        event_type: str,
        message: FeishuInboundMessage,
        workflow_response: GatewayMessageResponse,
        follow_up: dict[str, object],
    ) -> dict[str, object]:
        return {
            "code": 0,
            "msg": "ok",
            "event_type": event_type,
            "user_id": message.user_id,
            "chat_id": message.chat_id,
            "message_id": message.message_id,
            "gateway_response": {
                "request_id": workflow_response.request_id,
                "chain_request_id": workflow_response.chain_request_id,
                "run_session_id": workflow_response.run_session_id,
                "intent": workflow_response.intent,
                "message": workflow_response.message,
                "token_usage": workflow_response.token_usage.model_dump(),
                "task_id": workflow_response.task_id,
            },
            "automation_follow_up": follow_up,
        }

    def _continue_workflow(
        self,
        workflow_response: GatewayMessageResponse,
    ) -> dict[str, object]:
        auto_approve_plan = self.settings.resolved_sleep_coding_worker_auto_approve_plan
        if workflow_response.intent == "general":
            poll = self.automation.process_worker_poll_async(
                SleepCodingWorkerPollRequest(
                    auto_approve_plan=auto_approve_plan,
                )
            )
            return {
                "triggered": True,
                "mode": "worker_poll",
                "auto_approve_plan": poll.auto_approve_plan,
                "claimed_count": poll.claimed_count,
                "task_ids": [task.task_id for task in poll.tasks],
            }
        if workflow_response.intent == "sleep_coding" and workflow_response.task_id:
            if not auto_approve_plan:
                return {
                    "triggered": False,
                    "mode": "task_action",
                    "reason": "awaiting_confirmation",
                    "task_id": workflow_response.task_id,
                }
            task = self.automation.handle_sleep_coding_action_async(
                workflow_response.task_id,
                "approve_plan",
            )
            return {
                "triggered": True,
                "mode": "task_action",
                "action": "approve_plan",
                "task_id": task.task_id,
                "status": task.status,
            }
        return {
            "triggered": False,
            "mode": "noop",
            "reason": "no_follow_up_required",
        }
