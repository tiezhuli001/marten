from __future__ import annotations

import hashlib
import json
import time
import unittest
from datetime import UTC, datetime
from typing import Any

from app.agents.code_review_agent import ReviewService
from app.agents.main_agent import MainAgentService
from app.agents.ralph import SleepCodingService
from app.channel.feishu import FeishuWebhookService
from app.control.gateway import GatewayControlPlaneService
from app.control.sleep_coding_worker import SleepCodingWorkerService
from app.control.workflow import GatewayWorkflowService
from app.core.config import Settings
from app.infra.diagnostics import IntegrationDiagnosticsService
from app.ledger.service import TokenLedgerService
from app.models.schemas import MainAgentIntakeRequest, SleepCodingTask
from app.control.automation import AutomationService
from app.control.session_registry import SessionRegistryService
from app.control.task_registry import TaskRegistryService


def _load_live_test_config(settings: Settings) -> dict[str, Any]:
    config = settings.platform_config.get("live_test", {})
    return config if isinstance(config, dict) else {}


def _build_live_test_settings(settings: Settings, live_config: dict[str, Any]) -> Settings:
    return settings.model_copy(
        update={
            "llm_request_timeout_seconds": float(live_config.get("llm_request_timeout_seconds", 30.0)),
            "llm_request_max_attempts": max(int(live_config.get("llm_request_max_attempts", 1)), 1),
            "llm_request_retry_base_delay_seconds": max(
                float(live_config.get("llm_request_retry_base_delay_seconds", 0.0)),
                0.0,
            ),
            "mcp_request_timeout_seconds": float(live_config.get("mcp_request_timeout_seconds", 20.0)),
        }
    )


def _default_live_issue_prompt(marker: str) -> str:
    return (
        "创建一个最小 sleep-coding issue。\n"
        "只改 `docs/internal/live-chain-validation.md`。\n"
        f"只追加一行 marker，且包含 `{marker}`。\n"
        "不要改其他文件。\n"
        "给出简短验证说明，便于 review 通过。"
    )


class LiveChainIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base_settings = Settings()
        cls.live_config = _load_live_test_config(base_settings)
        cls.settings = _build_live_test_settings(base_settings, cls.live_config)
        if not cls.live_config.get("enabled", False):
            raise unittest.SkipTest(
                "Live chain test is disabled. Set `platform.json -> live_test.enabled=true` to run it."
            )
        if cls.settings.app_env == "test":
            raise unittest.SkipTest("Live chain test requires a non-test app environment.")

        required_paths = {
            "models.json": cls.settings.resolved_models_config_path,
            "mcp.json": cls.settings.resolved_mcp_config_path,
            "platform.json": cls.settings.resolved_platform_config_path,
        }
        missing = [
            f"{name}={path}"
            for name, path in required_paths.items()
            if not path.exists()
        ]
        if missing:
            raise unittest.SkipTest(
                "Live chain test requires JSON-first runtime configs: " + ", ".join(missing)
            )

        readiness = IntegrationDiagnosticsService(cls.settings).get_live_readiness()
        if not readiness.get("ready", False):
            raise unittest.SkipTest(
                "Live chain test prerequisites are not ready: "
                + str(
                    {
                        "blocking_components": readiness.get("blocking_components"),
                        "next_action": readiness.get("next_action"),
                        "summary": readiness.get("summary"),
                    }
                )
            )

    def test_real_chain_uses_live_llm_mcp_review_and_feishu(self) -> None:
        marker = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        user_id = f"live-chain-{marker}"
        sleep_coding = SleepCodingService(settings=self.settings)
        review = ReviewService(settings=self.settings, sleep_coding=sleep_coding)
        worker = SleepCodingWorkerService(settings=self.settings, sleep_coding=sleep_coding)
        automation = AutomationService(
            settings=self.settings,
            sleep_coding=sleep_coding,
            review=review,
            worker=worker,
        )
        sessions = SessionRegistryService(self.settings)
        main_agent = MainAgentService(
            self.settings,
            ledger=sleep_coding.ledger,
            sessions=sessions,
        )
        control_plane = GatewayControlPlaneService(
            settings=self.settings,
            ledger=sleep_coding.ledger,
            main_agent=main_agent,
            sleep_coding=sleep_coding,
            sessions=sessions,
        )
        feishu = FeishuWebhookService(
            self.settings,
            workflow=GatewayWorkflowService(
                self.settings,
                control_plane=control_plane,
                automation=automation,
            ),
        )
        task_registry = TaskRegistryService(self.settings)
        ledger = TokenLedgerService(self.settings)

        intake = main_agent.intake(
            MainAgentIntakeRequest(
                user_id=user_id,
                source="live_test",
                content=self._build_issue_prompt(marker),
            )
        )
        self.assertIsNotNone(intake.control_task_id)
        self.assertIsNotNone(intake.issue.issue_number)
        self.assertFalse(intake.issue.is_dry_run)

        parent_task = task_registry.get_task(str(intake.control_task_id))
        intake_request_id = parent_task.payload.get("request_id")
        self.assertIsInstance(intake_request_id, str)
        issue_number = int(intake.issue.issue_number)

        raw_body, headers = self._build_feishu_request(
            user_id=user_id,
            content=f"写代码 issue #{issue_number}",
        )
        response = feishu.handle_event(raw_body, headers)

        automation_follow_up = response.get("automation_follow_up")
        self.assertIsInstance(automation_follow_up, dict)
        gateway_response = response.get("gateway_response")
        self.assertIsInstance(gateway_response, dict)
        gateway_request_id = gateway_response.get("request_id")
        self.assertIsInstance(gateway_request_id, str)
        gateway_chain_request_id = gateway_response.get("chain_request_id")
        self.assertIsInstance(gateway_chain_request_id, str)
        self.assertEqual(gateway_chain_request_id, intake_request_id)
        self.assertNotEqual(gateway_request_id, intake_request_id)
        task_id = self._extract_task_id(automation_follow_up)
        current_task = sleep_coding.get_task(task_id)
        if (
            not automation_follow_up.get("triggered", False)
            or current_task.status == "awaiting_confirmation"
        ):
            task = automation.handle_sleep_coding_action_async(task_id, "approve_plan")
            task_id = task.task_id

        task = self._wait_for_terminal_task(sleep_coding, automation, task_id)
        self.assertEqual(task.status, "approved", task.model_dump_json(indent=2))
        self.assertEqual(task.background_follow_up_status, "completed", task.model_dump_json(indent=2))
        self.assertEqual(task.kickoff_request_id, gateway_chain_request_id)
        self.assertFalse(task.issue.is_dry_run)
        self.assertIsNotNone(task.pull_request)
        self.assertIsNotNone(task.pull_request.pr_number)
        self.assertFalse(task.pull_request.is_dry_run)

        reviews = review.list_task_reviews(task.task_id)
        self.assertGreaterEqual(len(reviews), 1)
        latest_review = reviews[-1]
        self.assertEqual(latest_review.status, "approved")
        self.assertEqual(latest_review.run_mode, "real_run")
        self.assertGreater(latest_review.token_usage.total_tokens, 0)

        intake_usage = ledger.get_request_usage(str(intake_request_id))
        self.assertGreater(intake_usage.total_tokens, 0)
        total_usage = ledger.get_request_usage(str(gateway_chain_request_id))
        execution_usage = ledger.get_request_usage(str(gateway_chain_request_id), ["sleep_coding_execution"])
        review_usage = ledger.get_request_usage(str(gateway_chain_request_id), ["code_review"])
        self.assertGreater(total_usage.total_tokens, 0)
        self.assertGreater(execution_usage.total_tokens, 0)
        self.assertGreater(review_usage.total_tokens, 0)

        delivered_plan_notification = next(
            (
                event
                for event in task.events
                if event.event_type == "channel_notified"
                and event.payload.get("stage") == "plan_ready"
                and event.payload.get("delivered") is True
                and event.payload.get("is_dry_run") is False
            ),
            None,
        )
        self.assertIsNotNone(delivered_plan_notification)

        parent_events = task_registry.list_events(parent_task.task_id)
        self.assertTrue(any(event.event_type == "delivery.completed" for event in parent_events))

    def _build_issue_prompt(self, marker: str) -> str:
        configured = self.live_config.get("issue_prompt")
        if isinstance(configured, str) and configured.strip():
            return configured.format(marker=marker)
        return _default_live_issue_prompt(marker)

    def _build_feishu_request(self, *, user_id: str, content: str) -> tuple[bytes, dict[str, str]]:
        payload = {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": user_id}},
                "message": {
                    "message_id": f"om_{user_id}",
                    "chat_id": f"oc_{user_id}",
                    "message_type": "text",
                    "content": json.dumps({"text": content}, ensure_ascii=False),
                },
            },
            "token": self.settings.feishu_verification_token,
        }
        raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        timestamp = str(int(time.time()))
        nonce = f"nonce-{user_id}"
        signature = hashlib.sha256(
            f"{timestamp}{nonce}{self.settings.feishu_encrypt_key}".encode("utf-8") + raw_body
        ).hexdigest()
        headers = {
            "content-type": "application/json",
            "x-lark-request-timestamp": timestamp,
            "x-lark-request-nonce": nonce,
            "x-lark-signature": signature,
        }
        return raw_body, headers

    def _extract_task_id(self, automation_follow_up: dict[str, Any]) -> str:
        task_ids = automation_follow_up.get("task_ids")
        if isinstance(task_ids, list) and task_ids and isinstance(task_ids[0], str):
            return task_ids[0]
        task_id = automation_follow_up.get("task_id")
        if isinstance(task_id, str) and task_id:
            return task_id
        raise AssertionError(f"Live chain response does not include a task id: {automation_follow_up}")

    def _wait_for_terminal_task(
        self,
        sleep_coding: SleepCodingService,
        automation: AutomationService,
        task_id: str,
    ) -> SleepCodingTask:
        timeout_seconds = int(self.live_config.get("timeout_seconds", 900))
        poll_interval_seconds = max(float(self.live_config.get("poll_interval_seconds", 0.2)), 0.05)
        deadline = time.time() + timeout_seconds
        latest = sleep_coding.get_task(task_id)
        approval_requested = False
        while time.time() < deadline:
            latest = sleep_coding.get_task(task_id)
            if latest.status in {"failed", "cancelled", "needs_attention"}:
                return latest
            if latest.status == "awaiting_confirmation" and not approval_requested:
                latest = automation.handle_sleep_coding_action_async(task_id, "approve_plan")
                approval_requested = True
                if latest.status in {"failed", "cancelled"}:
                    return latest
            if latest.status == "approved" and latest.background_follow_up_status == "completed":
                return latest
            time.sleep(poll_interval_seconds)
        raise AssertionError(
            "Live chain task did not reach terminal state before timeout:\n"
            + latest.model_dump_json(indent=2)
        )


class LiveChainPrerequisiteContractTests(unittest.TestCase):
    def test_default_live_issue_prompt_is_minimal_and_single_target(self) -> None:
        prompt = _default_live_issue_prompt("20260324T000000Z")

        self.assertIn("docs/internal/live-chain-validation.md", prompt)
        self.assertIn("20260324T000000Z", prompt)
        self.assertIn("不要改其他文件", prompt)

    def test_build_live_test_settings_applies_faster_runtime_profile(self) -> None:
        settings = Settings(
            app_env="development",
            llm_request_timeout_seconds=30.0,
            llm_request_max_attempts=3,
            llm_request_retry_base_delay_seconds=1.0,
            mcp_request_timeout_seconds=30.0,
        )

        optimized = _build_live_test_settings(
            settings,
            {
                "llm_request_timeout_seconds": 12.0,
                "llm_request_max_attempts": 1,
                "llm_request_retry_base_delay_seconds": 0.0,
                "mcp_request_timeout_seconds": 10.0,
            },
        )

        self.assertEqual(optimized.resolved_llm_request_timeout_seconds, 12.0)
        self.assertEqual(optimized.resolved_llm_request_max_attempts, 1)
        self.assertEqual(optimized.resolved_llm_request_retry_base_delay_seconds, 0.0)
        self.assertEqual(optimized.mcp_request_timeout_seconds, 10.0)

    def test_live_prerequisite_message_points_to_diagnostics_truth(self) -> None:
        diagnostics = {
            "main_chain": {
                "live_ready": False,
                "live_blocking_components": ["github_mcp", "review_skill"],
                "acceptance_summary": "Live chain blocked: github_mcp, review_skill.",
                "next_action": "repair_github_mcp",
            }
        }

        failures = []
        main_chain = diagnostics.get("main_chain", {})
        if not main_chain.get("live_ready", False):
            failures.append(
                "main_chain="
                + str(
                    {
                        "live_blocking_components": main_chain.get("live_blocking_components"),
                        "next_action": main_chain.get("next_action"),
                        "acceptance_summary": main_chain.get("acceptance_summary"),
                    }
                )
            )

        self.assertEqual(
            failures,
            [
                "main_chain={'live_blocking_components': ['github_mcp', 'review_skill'], 'next_action': 'repair_github_mcp', 'acceptance_summary': 'Live chain blocked: github_mcp, review_skill.'}"
            ],
        )


if __name__ == "__main__":
    unittest.main()
