from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Mapping

from app.channel.endpoints import ChannelEndpointRegistry
from app.control.workflow import GatewayWorkflowService
from app.core.config import Settings
from app.models.schemas import GatewayMessageRequest, GatewayMessageResponse


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
        workflow: GatewayWorkflowService | None = None,
    ) -> None:
        self.settings = settings
        self.workflow = workflow or GatewayWorkflowService(settings)
        self.endpoints = ChannelEndpointRegistry(settings)

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
        session_key = self._build_session_key(message)
        workflow_result = self.workflow.run(
            GatewayMessageRequest(
                user_id=message.user_id,
                content=message.content,
                source="feishu",
                session_key=session_key,
                message_id=message.message_id,
                chat_id=message.chat_id,
                endpoint_id=self.endpoints.resolve_endpoint_id(
                    provider="feishu",
                    external_refs=[session_key, message.chat_id] if message.chat_id else [session_key],
                ),
            )
        )
        return self._build_ack_response(
            event_type,
            message,
            workflow_result.gateway_response,
            workflow_result.follow_up,
        )

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
            "accepted": True,
            "started": workflow_response.workflow_state in {"accepted", "running"},
            "completed": workflow_response.workflow_state == "completed",
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
                "source_endpoint_id": workflow_response.source_endpoint_id,
                "delivery_endpoint_id": workflow_response.delivery_endpoint_id,
                "workflow_state": workflow_response.workflow_state,
                "active_task_id": workflow_response.active_task_id,
            },
            "automation_follow_up": follow_up,
        }

    def _build_session_key(self, message: FeishuInboundMessage) -> str:
        if message.chat_id:
            return f"feishu:chat:{message.chat_id}"
        return message.user_id
