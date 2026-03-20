import hashlib
import json
import unittest

from app.core.config import Settings
from app.models.schemas import GatewayMessageResponse, TokenUsage
from app.channel.feishu import FeishuWebhookService


class FakeGatewayControlPlaneService:
    def __init__(self) -> None:
        self.requests = []

    def run(self, payload):
        self.requests.append(payload)
        return GatewayMessageResponse(
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
        )


class FakeAutomationService:
    def __init__(self) -> None:
        self.worker_polls = []
        self.task_actions = []

    def process_worker_poll_async(self, payload):
        self.worker_polls.append(payload)
        return type(
            "PollResponseStub",
            (),
            {
                "auto_approve_plan": bool(payload.auto_approve_plan),
                "claimed_count": 1,
                "tasks": [type("TaskStub", (), {"task_id": "task-worker-1"})()],
            },
        )()

    def handle_sleep_coding_action_async(self, task_id: str, action: str):
        self.task_actions.append((task_id, action))
        return type("TaskStub", (), {"task_id": task_id, "status": "in_review"})()

    def continue_gateway_workflow(self, *, intent: str, task_id: str | None):
        if intent == "general":
            payload = type("PollRequestStub", (), {"auto_approve_plan": True})()
            poll = self.process_worker_poll_async(payload)
            return {
                "triggered": True,
                "mode": "worker_poll",
                "auto_approve_plan": poll.auto_approve_plan,
                "claimed_count": poll.claimed_count,
                "task_ids": [task.task_id for task in poll.tasks],
            }
        if intent == "sleep_coding" and task_id:
            task = self.handle_sleep_coding_action_async(task_id, "approve_plan")
            return {
                "triggered": True,
                "mode": "task_action",
                "action": "approve_plan",
                "task_id": task.task_id,
                "status": task.status,
            }
        return {"triggered": False, "mode": "noop", "reason": "no_follow_up_required"}


class FeishuWebhookServiceTests(unittest.TestCase):
    def test_handle_url_verification_returns_challenge(self) -> None:
        service = FeishuWebhookService(
            Settings(app_env="test", feishu_verification_token="token-1", feishu_encrypt_key=None),
            control_plane=FakeGatewayControlPlaneService(),
            automation=FakeAutomationService(),
        )
        payload = {
            "type": "url_verification",
            "challenge": "challenge-value",
            "token": "token-1",
        }

        response = service.handle_event(json.dumps(payload).encode("utf-8"), {})

        self.assertEqual(response, {"challenge": "challenge-value"})

    def test_handle_message_event_maps_user_and_calls_workflow(self) -> None:
        control_plane = FakeGatewayControlPlaneService()
        automation = FakeAutomationService()
        settings = Settings(
            app_env="test",
            feishu_verification_token="token-1",
            feishu_encrypt_key="encrypt-key",
            platform_config_path="/tmp/does-not-exist-platform.json",
            sleep_coding_worker_auto_approve_plan=True,
        )
        service = FeishuWebhookService(settings, control_plane=control_plane, automation=automation)
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
        self.assertEqual(control_plane.requests[0].user_id, "feishu:ou_123")
        self.assertEqual(control_plane.requests[0].source, "feishu")
        self.assertEqual(control_plane.requests[0].content, "请帮我总结今天进度")
        self.assertTrue(response["automation_follow_up"]["triggered"])
        self.assertEqual(response["automation_follow_up"]["mode"], "worker_poll")
        self.assertEqual(response["automation_follow_up"]["claimed_count"], 1)
        self.assertEqual(response["gateway_response"]["task_id"], "task-feishu-1")
        self.assertEqual(response["gateway_response"]["chain_request_id"], "chain-feishu-1")
        self.assertEqual(len(automation.worker_polls), 1)

    def test_handle_message_event_rejects_invalid_signature(self) -> None:
        service = FeishuWebhookService(
            Settings(
                app_env="test",
                feishu_verification_token="token-1",
                feishu_encrypt_key="encrypt-key",
            ),
            control_plane=FakeGatewayControlPlaneService(),
            automation=FakeAutomationService(),
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
