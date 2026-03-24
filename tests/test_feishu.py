import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from app.control.workflow import GatewayWorkflowResult
from app.core.config import Settings
from app.models.schemas import GatewayMessageResponse, TokenUsage
from app.channel.feishu import FeishuWebhookService


class FakeGatewayWorkflowService:
    def __init__(self) -> None:
        self.requests = []
        self.follow_ups = []

    def run(self, payload):
        self.requests.append(payload)
        follow_up = {
            "triggered": True,
            "mode": "worker_poll",
            "auto_approve_plan": True,
            "claimed_count": 1,
            "task_ids": ["task-worker-1"],
        }
        self.follow_ups.append(follow_up)
        return GatewayWorkflowResult(
            gateway_response=GatewayMessageResponse(
                request_id="req-feishu-1",
                chain_request_id="chain-feishu-1",
                intent="general",
                message="processed",
                token_usage=TokenUsage(
                    prompt_tokens=12,
                    completion_tokens=6,
                    total_tokens=18,
                    provider="openai",
                    model_name="gpt-4.1-mini",
                    cost_usd=0.0000144,
                ),
                task_id="task-feishu-1",
            ),
            follow_up=follow_up,
        )


class FeishuWebhookServiceTests(unittest.TestCase):
    def test_handle_url_verification_returns_challenge(self) -> None:
        service = FeishuWebhookService(
            Settings(app_env="test", feishu_verification_token="token-1", feishu_encrypt_key=None),
            workflow=FakeGatewayWorkflowService(),
        )
        payload = {
            "type": "url_verification",
            "challenge": "challenge-value",
            "token": "token-1",
        }

        response = service.handle_event(json.dumps(payload).encode("utf-8"), {})

        self.assertEqual(response, {"challenge": "challenge-value"})

    def test_handle_message_event_maps_user_and_calls_workflow(self) -> None:
        workflow = FakeGatewayWorkflowService()
        settings = Settings(
            app_env="test",
            feishu_verification_token="token-1",
            feishu_encrypt_key="encrypt-key",
            platform_config_path="/tmp/does-not-exist-platform.json",
            sleep_coding_worker_auto_approve_plan=True,
        )
        service = FeishuWebhookService(settings, workflow=workflow)
        payload = {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_123"}},
                "message": {
                    "message_id": "om_123",
                    "chat_id": "oc_123",
                    "message_type": "text",
                    "content": json.dumps({"text": "请帮我总结今天进度"}),
                },
            },
            "token": "token-1",
        }
        raw_body = json.dumps(payload).encode("utf-8")
        headers = self._signed_headers(raw_body, settings.feishu_encrypt_key or "")

        response = service.handle_event(raw_body, headers)

        self.assertEqual(response["code"], 0)
        self.assertEqual(response["event_type"], "im.message.receive_v1")
        self.assertEqual(response["user_id"], "feishu:ou_123")
        self.assertEqual(workflow.requests[0].user_id, "feishu:ou_123")
        self.assertEqual(workflow.requests[0].source, "feishu")
        self.assertEqual(workflow.requests[0].message_id, "om_123")
        self.assertEqual(workflow.requests[0].session_key, "feishu:chat:oc_123")
        self.assertEqual(workflow.requests[0].content, "请帮我总结今天进度")
        self.assertTrue(response["accepted"])
        self.assertTrue(response["started"])
        self.assertFalse(response["completed"])
        self.assertTrue(response["automation_follow_up"]["triggered"])
        self.assertEqual(response["automation_follow_up"]["mode"], "worker_poll")
        self.assertEqual(response["automation_follow_up"]["claimed_count"], 1)
        self.assertEqual(response["gateway_response"]["task_id"], "task-feishu-1")
        self.assertEqual(response["gateway_response"]["chain_request_id"], "chain-feishu-1")
        self.assertEqual(len(workflow.follow_ups), 1)

    def test_handle_message_event_rejects_invalid_signature(self) -> None:
        service = FeishuWebhookService(
            Settings(
                app_env="test",
                feishu_verification_token="token-1",
                feishu_encrypt_key="encrypt-key",
            ),
            workflow=FakeGatewayWorkflowService(),
        )
        payload = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_123"}},
                "message": {
                    "message_type": "text",
                    "content": json.dumps({"text": "hello"}),
                },
            },
            "token": "token-1",
        }

        with self.assertRaisesRegex(PermissionError, "Invalid Feishu signature"):
            service.handle_event(
                json.dumps(payload).encode("utf-8"),
                {
                    "X-Lark-Request-Timestamp": "1700000000",
                    "X-Lark-Request-Nonce": "nonce-1",
                    "X-Lark-Signature": "bad-signature",
                },
            )

    def test_handle_message_event_prefers_canonical_chat_endpoint_mapping(self) -> None:
        workflow = FakeGatewayWorkflowService()
        with tempfile.TemporaryDirectory() as temp_dir:
            platform_json = Path(temp_dir) / "platform.json"
            platform_json.write_text(
                json.dumps(
                    {
                        "channel": {
                            "provider": "feishu",
                            "default_endpoint": "fallback-entry",
                            "endpoints": {
                                "fallback-entry": {
                                    "provider": "feishu",
                                    "mode": "primary",
                                    "entry_enabled": True,
                                    "delivery_enabled": True,
                                },
                                "chat-entry": {
                                    "provider": "feishu",
                                    "mode": "primary",
                                    "entry_enabled": True,
                                    "delivery_enabled": True,
                                    "external_refs": ["feishu:chat:oc_123"],
                                    "delivery_policy": {
                                        "mode": "fixed_endpoint",
                                        "endpoint_id": "feishu-delivery",
                                    },
                                },
                                "feishu-delivery": {
                                    "provider": "feishu",
                                    "mode": "delivery",
                                    "entry_enabled": False,
                                    "delivery_enabled": True,
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings(
                app_env="test",
                feishu_verification_token="token-1",
                feishu_encrypt_key="encrypt-key",
                platform_config_path=str(platform_json),
            )
            service = FeishuWebhookService(settings, workflow=workflow)
            payload = {
                "schema": "2.0",
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {"sender_id": {"open_id": "ou_123"}},
                    "message": {
                        "message_id": "om_123",
                        "chat_id": "oc_123",
                        "message_type": "text",
                        "content": json.dumps({"text": "请开始处理这个需求"}),
                    },
                },
                "token": "token-1",
            }
            raw_body = json.dumps(payload).encode("utf-8")
            headers = self._signed_headers(raw_body, settings.feishu_encrypt_key or "")

            response = service.handle_event(raw_body, headers)

        self.assertEqual(response["code"], 0)
        self.assertEqual(workflow.requests[0].endpoint_id, "chat-entry")

    def _signed_headers(self, raw_body: bytes, encrypt_key: str) -> dict[str, str]:
        timestamp = "1700000000"
        nonce = "nonce-1"
        signature = hashlib.sha256(
            f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + raw_body
        ).hexdigest()
        return {
            "X-Lark-Request-Timestamp": timestamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": signature,
        }


if __name__ == "__main__":
    unittest.main()
