import unittest
import json
import tempfile
import threading
import time
from pathlib import Path

from app.core.config import Settings
from app.control.gateway import GatewayControlPlaneService
from app.control.routing import classify_intent, resolve_route
from app.control.task_registry import TaskRegistryService
from app.control.workflow import GatewayWorkflowService
from app.control.session_registry import SessionRegistryService
from app.models.schemas import (
    GatewayMessageRequest,
    GitHubIssueResult,
    MainAgentIntakeResponse,
    TokenUsage,
)


class FakeMainAgentService:
    def __init__(self, tasks: TaskRegistryService | None = None) -> None:
        self.calls = 0
        self.tasks = tasks

    def intake(self, payload):  # noqa: ANN001
        self.calls += 1
        issue_number = 100 + self.calls
        control_task_id = f"control-task-{issue_number}"
        if self.tasks is not None:
            created = self.tasks.create_task(
                task_type="main_agent_intake",
                agent_id="main-agent",
                status="issue_created",
                user_id=payload.user_id,
                source=payload.source,
                repo="tiezhuli001/marten",
                issue_number=issue_number,
                title="Gateway-created issue",
                external_ref=f"github_issue:tiezhuli001/marten#{issue_number}",
                payload={},
            )
            control_task_id = created.task_id
        return MainAgentIntakeResponse(
            mode="coding_handoff",
            issue=GitHubIssueResult(
                issue_number=issue_number,
                title="Gateway-created issue",
                body=payload.content,
                html_url=f"https://github.com/tiezhuli001/marten/issues/{issue_number}",
                labels=["agent:ralph", "workflow:sleep-coding"],
                is_dry_run=True,
            ),
            message=f"Main Agent created #{issue_number}: Gateway-created issue",
            token_usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                step_name="main_agent_issue_intake",
            ),
            control_task_id=control_task_id,
        )


class FakeSessionRegistryService:
    def __init__(self) -> None:
        self.payload_updates = []
        self.get_or_create_calls = []
        self.run_parent_session_ids = []
        self.sessions_by_id = {}
        self.receipts = {}

    def get_or_create_session(self, **kwargs):  # noqa: ANN003
        self.get_or_create_calls.append(kwargs)
        session_id = kwargs.get("external_ref", "session-1")
        parent_session_id = kwargs.get("parent_session_id")
        if kwargs.get("session_type") == "run_session":
            self.run_parent_session_ids.append(parent_session_id)
        session = type(
            "SessionStub",
            (),
            {
                "session_id": session_id,
                "payload": kwargs.get("payload", {}),
                "parent_session_id": parent_session_id,
                "external_ref": kwargs.get("external_ref"),
            },
        )()
        self.sessions_by_id[session_id] = session
        return session

    def set_active_agent(self, session_id: str, agent_id: str):  # noqa: ANN001
        self.payload_updates.append((session_id, agent_id))
        return type("SessionStub", (), {"session_id": session_id, "payload": {"active_agent": agent_id}})()

    def update_session_payload(self, session_id: str, payload_patch: dict):  # noqa: ANN001
        session = self.sessions_by_id[session_id]
        updated_payload = {**getattr(session, "payload", {}), **payload_patch}
        updated = type(
            "SessionStub",
            (),
            {
                "session_id": session_id,
                "payload": updated_payload,
                "parent_session_id": getattr(session, "parent_session_id", None),
                "external_ref": getattr(session, "external_ref", None),
            },
        )()
        self.sessions_by_id[session_id] = updated
        return updated

    def get_session(self, session_id: str):  # noqa: ANN001
        if session_id not in self.sessions_by_id:
            self.sessions_by_id[session_id] = type(
                "SessionStub",
                (),
                {
                    "session_id": session_id,
                    "payload": {},
                    "parent_session_id": None,
                    "external_ref": session_id,
                },
            )()
        return self.sessions_by_id[session_id]

    def find_inbound_receipt(self, dedupe_key: str):  # noqa: ANN001
        return self.receipts.get(dedupe_key)

    def record_inbound_receipt(self, dedupe_key: str, response_payload: dict):  # noqa: ANN001
        self.receipts[dedupe_key] = response_payload
        return response_payload

    def get_execution_lane(self, lane_key: str | None = None):  # noqa: ANN001
        return type("ExecutionLaneSnapshotStub", (), {"lane_key": lane_key or "self_host:default", "active_task_id": None, "queued_task_ids": []})()

    def acquire_execution_lane(self, task_id: str, lane_key: str | None = None):  # noqa: ANN001
        return type(
            "ExecutionLaneDecisionStub",
            (),
            {
                "disposition": "accepted",
                "snapshot": self.get_execution_lane(lane_key),
            },
        )()

    def release_execution_lane(self, task_id: str, lane_key: str | None = None):  # noqa: ANN001
        return type(
            "ExecutionLaneDecisionStub",
            (),
            {
                "disposition": "released",
                "snapshot": self.get_execution_lane(lane_key),
            },
        )()

    def record_session_turn(
        self,
        session_id: str,
        *,
        request_id: str,
        chain_request_id: str,
        intent: str,
        workflow_state: str,
        task_id: str | None,
        source_endpoint_id: str,
        delivery_endpoint_id: str,
        run_session_id: str | None = None,
    ):  # noqa: ANN001
        session = self.get_session(session_id)
        updated_payload = {
            **getattr(session, "payload", {}),
            "last_request_id": request_id,
            "last_chain_request_id": chain_request_id,
            "last_intent": intent,
            "last_workflow_state": workflow_state,
            "last_task_id": task_id,
            "source_endpoint_id": source_endpoint_id,
            "delivery_endpoint_id": delivery_endpoint_id,
            "last_run_session_id": run_session_id,
        }
        return self.update_session_payload(session_id, updated_payload)


class FakeLedgerService:
    def record_request(self, **kwargs):  # noqa: ANN003
        return kwargs["usage"]

    def get_usage_summary(self, query: str):  # noqa: ANN001
        return f"usage summary for {query}"


class FakeTaskRegistryService:
    def __init__(self, parent_request_id: str | None = None) -> None:
        self.parent_request_id = parent_request_id
        self.events = []
        self.tasks = {}

    def find_parent_for_issue(self, repo: str, issue_number: int):  # noqa: ANN001
        if self.parent_request_id is None:
            return None
        return type(
            "TaskStub",
            (),
            {
                "task_id": "parent-task-55",
                "payload": {
                    "request_id": self.parent_request_id,
                    "user_session_id": "user-session-55",
                },
            },
        )()

    def append_event(self, task_id: str, event_type: str, payload: dict):  # noqa: ANN001
        self.events.append((task_id, event_type, payload))
        return None

    def update_task(self, task_id: str, **kwargs):  # noqa: ANN003
        payload_patch = kwargs.get("payload_patch", {})
        current = self.tasks.get(task_id, {"task_id": task_id, "payload": {}})
        current["payload"] = {**current.get("payload", {}), **payload_patch}
        self.tasks[task_id] = current
        return type("TaskStub", (), current)()

    def get_task(self, task_id: str):  # noqa: ANN001
        current = self.tasks.get(task_id, {"task_id": task_id, "payload": {}})
        return type("TaskStub", (), current)()


class FakeSleepCodingService:
    def __init__(self) -> None:
        self.requests = []

    def start_task(self, payload):  # noqa: ANN001
        self.requests.append(payload)
        return type(
            "TaskStub",
            (),
            {
                "task_id": "sleep-task-55",
                "status": "awaiting_confirmation",
                "head_branch": "codex/issue-55-sleep-coding",
                "control_task_id": None,
            },
        )()


class FakeAutomationService:
    def __init__(self) -> None:
        self.calls = 0

    def continue_gateway_workflow(self, *, intent: str, task_id: str | None):  # noqa: ANN001
        self.calls += 1
        return {"triggered": True, "mode": "worker_poll", "intent": intent, "task_id": task_id}


class GatewayRoutingTests(unittest.TestCase):
    def test_issue_pr_review_words_do_not_bypass_general_intake(self) -> None:
        self.assertEqual(classify_intent("请创建一个 issue 并后续补 review"), "general")
        self.assertEqual(classify_intent("这次 PR 需要补一条测试"), "general")

    def test_explicit_ralph_mention_routes_to_sleep_coding(self) -> None:
        route = resolve_route("@ralph 请帮我接手 issue #55")

        self.assertEqual(route.intent, "sleep_coding")
        self.assertEqual(route.target_agent, "ralph")
        self.assertTrue(route.direct_mention)

    def test_review_mention_is_kept_on_main_agent_entry(self) -> None:
        route = resolve_route("让 review 看一下这个需求")

        self.assertEqual(route.intent, "general")
        self.assertEqual(route.target_agent, "main-agent")
        self.assertFalse(route.direct_mention)

    def test_general_request_with_issue_word_still_creates_issue_via_main_agent(self) -> None:
        sessions = FakeSessionRegistryService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            main_agent=FakeMainAgentService(),
            sessions=sessions,
            ledger=FakeLedgerService(),
            tasks=FakeTaskRegistryService(),
        )

        response = service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                content="请帮我整理这个需求并创建一个 issue：补一条真实链路验证测试。",
            )
        )

        self.assertEqual(response.intent, "general")
        self.assertEqual(response.task_id, "control-task-101")
        self.assertEqual(response.token_usage.step_name, "main_agent_issue_intake")
        self.assertEqual(response.chain_request_id, response.request_id)
        self.assertIsNotNone(response.run_session_id)
        self.assertEqual(sessions.payload_updates[-1][1], "main-agent")

    def test_gateway_prefers_explicit_session_key_for_canonical_user_session_ref(self) -> None:
        sessions = FakeSessionRegistryService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            main_agent=FakeMainAgentService(),
            sessions=sessions,
            ledger=FakeLedgerService(),
            tasks=FakeTaskRegistryService(),
        )

        service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                session_key="feishu:chat:oc_123",
                content="请帮我整理这个需求并创建一个 issue：补一条真实链路验证测试。",
            )
        )

        self.assertEqual(sessions.get_or_create_calls[0]["external_ref"], "feishu:chat:oc_123")

    def test_sleep_coding_request_inherits_chain_request_id_from_parent_issue(self) -> None:
        sleep_coding = FakeSleepCodingService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            sleep_coding=sleep_coding,
            sessions=FakeSessionRegistryService(),
            ledger=FakeLedgerService(),
            tasks=FakeTaskRegistryService(parent_request_id="req-parent-55"),
        )

        response = service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                content="写代码 issue #55",
            )
        )

        self.assertEqual(response.intent, "sleep_coding")
        self.assertEqual(response.request_id != response.chain_request_id, True)
        self.assertEqual(response.chain_request_id, "req-parent-55")
        self.assertEqual(sleep_coding.requests[0].request_id, "req-parent-55")

    def test_sleep_coding_request_reuses_linked_user_session_as_run_parent(self) -> None:
        sleep_coding = FakeSleepCodingService()
        sessions = FakeSessionRegistryService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            sleep_coding=sleep_coding,
            sessions=sessions,
            ledger=FakeLedgerService(),
            tasks=FakeTaskRegistryService(parent_request_id="req-parent-55"),
        )

        service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                content="写代码 issue #55",
            )
        )

        self.assertEqual(sessions.run_parent_session_ids[-1], "user-session-55")

    def test_gateway_workflow_queues_second_general_request_while_first_task_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(app_env="test", database_url=f"sqlite:///{Path(temp_dir) / 'gateway.db'}")
            sessions = SessionRegistryService(settings)
            tasks = TaskRegistryService(settings)
            workflow = GatewayWorkflowService(
                settings=settings,
                control_plane=GatewayControlPlaneService(
                    settings=settings,
                    main_agent=FakeMainAgentService(tasks=tasks),
                    sessions=sessions,
                    tasks=tasks,
                    ledger=FakeLedgerService(),
                ),
                automation=FakeAutomationService(),
            )

            first = workflow.run(
                GatewayMessageRequest(
                    user_id="user-1",
                    source="manual",
                    content="请实现第一个 coding 请求。",
                )
            )
            second = workflow.run(
                GatewayMessageRequest(
                    user_id="user-2",
                    source="manual",
                    content="请实现第二个 coding 请求。",
                )
            )

            queued_task = tasks.get_task(second.gateway_response.task_id)

            self.assertEqual(first.gateway_response.workflow_state, "accepted")
            self.assertEqual(second.gateway_response.workflow_state, "queued")
            self.assertEqual(second.gateway_response.active_task_id, first.gateway_response.task_id)
            self.assertEqual(first.follow_up["triggered"], True)
            self.assertEqual(second.follow_up["triggered"], False)
            self.assertEqual(second.follow_up["reason"], "queued")
            self.assertEqual(queued_task.payload["queue_status"], "queued")
            self.assertEqual(queued_task.payload["active_task_id"], first.gateway_response.task_id)

    def test_same_feishu_session_records_last_task_linkage_after_stats_then_coding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(app_env="test", database_url=f"sqlite:///{Path(temp_dir) / 'gateway.db'}")
            sessions = SessionRegistryService(settings)
            tasks = TaskRegistryService(settings)
            service = GatewayControlPlaneService(
                settings=settings,
                main_agent=FakeMainAgentService(tasks=tasks),
                sessions=sessions,
                tasks=tasks,
                ledger=FakeLedgerService(),
            )

            stats = service.run(
                GatewayMessageRequest(
                    user_id="feishu:test-user",
                    source="feishu",
                    session_key="feishu:chat:oc_123",
                    content="今天 token 用量怎么样？",
                )
            )
            coding = service.run(
                GatewayMessageRequest(
                    user_id="feishu:test-user",
                    source="feishu",
                    session_key="feishu:chat:oc_123",
                    content="请整理这个需求并创建 issue 进入开发流程。",
                )
            )

            user_session = sessions.find_by_external_ref("feishu:chat:oc_123")

            self.assertIsNotNone(user_session)
            assert user_session is not None
            self.assertEqual(stats.workflow_state, "completed")
            self.assertEqual(coding.workflow_state, "accepted")
            self.assertEqual(user_session.payload["last_task_id"], coding.task_id)
            self.assertEqual(user_session.payload["last_workflow_state"], "accepted")
            self.assertEqual(user_session.payload["last_chain_request_id"], coding.chain_request_id)

    def test_explicit_ralph_mention_starts_sleep_coding_even_without_keyword(self) -> None:
        sleep_coding = FakeSleepCodingService()
        sessions = FakeSessionRegistryService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            sleep_coding=sleep_coding,
            sessions=sessions,
            ledger=FakeLedgerService(),
            tasks=FakeTaskRegistryService(),
        )

        response = service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                content="@ralph issue #55",
            )
        )

        self.assertEqual(response.intent, "sleep_coding")
        self.assertEqual(sleep_coding.requests[0].issue_number, 55)
        self.assertEqual(sessions.payload_updates[-1][1], "ralph")

    def test_disallowed_direct_handoff_falls_back_and_records_routing_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            platform_json = root / "platform.json"
            platform_json.write_text(
                json.dumps(
                    {
                        "channel": {
                            "provider": "feishu",
                            "default_endpoint": "main-entry",
                            "endpoints": {
                                "main-entry": {
                                    "provider": "feishu",
                                    "mode": "primary",
                                    "entry_enabled": True,
                                    "delivery_enabled": True,
                                    "default_agent": "main-agent",
                                    "default_workflow": "general",
                                    "allowed_handoffs": [],
                                }
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            sessions = FakeSessionRegistryService()
            tasks = FakeTaskRegistryService()
            service = GatewayControlPlaneService(
                settings=Settings(
                    app_env="test",
                    database_url=f"sqlite:///{root / 'gateway.db'}",
                    platform_config_path=str(platform_json),
                ),
                main_agent=FakeMainAgentService(),
                sessions=sessions,
                ledger=FakeLedgerService(),
                tasks=tasks,
            )

            response = service.run(
                GatewayMessageRequest(
                    user_id="feishu:test-user",
                    source="feishu",
                    endpoint_id="main-entry",
                    content="@ralph 请接手 issue #55",
                )
            )

            self.assertEqual(response.intent, "general")
            self.assertEqual(response.task_id, "control-task-101")
            self.assertEqual(sessions.payload_updates[-1][1], "main-agent")
            self.assertEqual(len(tasks.events), 2)
            self.assertEqual(tasks.events[-1][0], "control-task-101")
            self.assertEqual(tasks.events[-1][1], "routing_failure")
            self.assertEqual(tasks.events[-1][2]["requested_agent"], "ralph")
            self.assertEqual(tasks.events[-1][2]["reason"], "handoff_not_allowed")

    def test_duplicate_message_id_reuses_recorded_gateway_response(self) -> None:
        sessions = FakeSessionRegistryService()
        main_agent = FakeMainAgentService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            main_agent=main_agent,
            sessions=sessions,
            ledger=FakeLedgerService(),
            tasks=FakeTaskRegistryService(),
        )

        first = service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                message_id="om_123",
                session_key="feishu:chat:oc_123",
                content="请帮我整理这个需求并创建一个 issue：补一条真实链路验证测试。",
            )
        )
        second = service.run(
            GatewayMessageRequest(
                user_id="feishu:test-user",
                source="feishu",
                message_id="om_123",
                session_key="feishu:chat:oc_123",
                content="请帮我整理这个需求并创建一个 issue：补一条真实链路验证测试。",
            )
        )

        self.assertEqual(main_agent.calls, 1)
        self.assertEqual(second.request_id, first.request_id)
        self.assertEqual(second.chain_request_id, first.chain_request_id)
        self.assertEqual(second.task_id, first.task_id)

    def test_same_session_requests_are_serialized_by_lane(self) -> None:
        class BlockingMainAgentService(FakeMainAgentService):
            def __init__(self) -> None:
                super().__init__()
                self.started = []
                self.release_first = threading.Event()
                self.first_started = threading.Event()
                self._lock = threading.Lock()

            def intake(self, payload):  # noqa: ANN001
                with self._lock:
                    self.started.append(time.time())
                    current_call = len(self.started)
                    if current_call == 1:
                        self.first_started.set()
                if current_call == 1:
                    self.release_first.wait(timeout=2)
                return super().intake(payload)

        sessions = FakeSessionRegistryService()
        main_agent = BlockingMainAgentService()
        service = GatewayControlPlaneService(
            settings=Settings(app_env="test", database_url="sqlite:////tmp/test-gateway.db"),
            main_agent=main_agent,
            sessions=sessions,
            ledger=FakeLedgerService(),
            tasks=FakeTaskRegistryService(),
        )
        results = []

        def _run_request(content: str) -> None:
            results.append(
                service.run(
                    GatewayMessageRequest(
                        user_id="feishu:test-user",
                        source="feishu",
                        session_key="feishu:chat:oc_123",
                        content=content,
                    )
                )
            )

        first = threading.Thread(target=_run_request, args=("请创建一个 issue：任务一",))
        second = threading.Thread(target=_run_request, args=("请创建一个 issue：任务二",))

        first.start()
        self.assertTrue(main_agent.first_started.wait(timeout=1))
        second.start()
        time.sleep(0.2)
        self.assertEqual(len(main_agent.started), 1)
        main_agent.release_first.set()
        first.join(timeout=2)
        second.join(timeout=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(len(main_agent.started), 2)

    def test_same_session_duplicate_message_is_idempotent_under_concurrency(self) -> None:
        class BlockingMainAgentService(FakeMainAgentService):
            def __init__(self) -> None:
                super().__init__()
                self.release_first = threading.Event()
                self.first_started = threading.Event()

            def intake(self, payload):  # noqa: ANN001
                if self.calls == 0:
                    self.first_started.set()
                    self.release_first.wait(timeout=2)
                return super().intake(payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(app_env="test", database_url=f"sqlite:///{Path(temp_dir) / 'gateway.db'}")
            sessions = SessionRegistryService(settings)
            tasks = TaskRegistryService(settings)
            main_agent = BlockingMainAgentService()
            main_agent.tasks = tasks
            service = GatewayControlPlaneService(
                settings=settings,
                main_agent=main_agent,
                sessions=sessions,
                ledger=FakeLedgerService(),
                tasks=tasks,
            )
            results = []

            def _run_request() -> None:
                results.append(
                    service.run(
                        GatewayMessageRequest(
                            user_id="feishu:test-user",
                            source="feishu",
                            session_key="feishu:chat:oc_123",
                            message_id="om_same",
                            content="请创建一个 issue：重复消息",
                        )
                    )
                )

            first = threading.Thread(target=_run_request)
            second = threading.Thread(target=_run_request)

            first.start()
            self.assertTrue(main_agent.first_started.wait(timeout=1))
            second.start()
            time.sleep(0.2)
            self.assertEqual(main_agent.calls, 0)
            main_agent.release_first.set()
            first.join(timeout=2)
            second.join(timeout=2)

            self.assertEqual(len(results), 2)
            self.assertEqual(main_agent.calls, 1)
            self.assertEqual(results[0].request_id, results[1].request_id)
            self.assertEqual(results[0].chain_request_id, results[1].chain_request_id)
            self.assertEqual(results[0].task_id, results[1].task_id)


if __name__ == "__main__":
    unittest.main()
