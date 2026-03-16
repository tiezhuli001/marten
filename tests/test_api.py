import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import get_review_service
from app.models.schemas import ReviewActionRequest, ReviewRun, ReviewRunRequest, ReviewSource


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

        class FakeReviewService:
            def start_review(self, payload: ReviewRunRequest) -> ReviewRun:
                return ReviewRun(
                    review_id="review-1",
                    source=payload.source,
                    status="completed",
                    artifact_path="docs/review-runs/local-review-review-1.md",
                    comment_url=payload.source.url,
                    summary="Review complete",
                    content="## Code Review Agent",
                    run_mode="dry_run",
                    task_id=payload.source.task_id,
                    created_at="2026-03-16 00:00:00",
                    updated_at="2026-03-16 00:00:00",
                    reviewed_at="2026-03-16 00:00:00",
                )

            def get_review(self, review_id: str) -> ReviewRun:
                return self.start_review(
                    ReviewRunRequest(source=ReviewSource(source_type="local_code", local_path="."))
                )

            def apply_action(self, review_id: str, payload: ReviewActionRequest) -> ReviewRun:
                review = self.get_review(review_id)
                return review.model_copy(
                    update={"status": "approved" if payload.action == "approve_review" else "changes_requested"}
                )

            def trigger_for_task(self, task_id: str) -> ReviewRun:
                return self.start_review(
                    ReviewRunRequest(
                        source=ReviewSource(source_type="sleep_coding_task", task_id=task_id)
                    )
                )

        app.dependency_overrides[get_review_service] = lambda: FakeReviewService()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_gateway_message_endpoint(self) -> None:
        response = self.client.post(
            "/gateway/message",
            json={
                "user_id": "user-1",
                "content": "帮我统计最近7天 token 消耗",
                "source": "manual",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["intent"], "stats_query")
        self.assertIn("token_usage", payload)

    def test_sleep_coding_task_endpoint(self) -> None:
        response = self.client.post(
            "/tasks/sleep-coding",
            json={
                "issue_number": 42,
                "repo": "tiezhuli001/youmeng-gateway",
                "issue_title": "Implement sleep coding API",
                "issue_body": "Need the task creation and review endpoints.",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "awaiting_confirmation")
        self.assertEqual(payload["issue_number"], 42)
        self.assertIn("agent:ralph", payload["issue"]["labels"])

    def test_gateway_message_creates_sleep_coding_task_when_issue_number_is_present(self) -> None:
        response = self.client.post(
            "/gateway/message",
            json={
                "user_id": "user-1",
                "content": "请处理 issue 42 并准备 pr",
                "source": "manual",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["intent"], "sleep_coding")
        self.assertIn("Status=awaiting_confirmation", payload["message"])

    def test_gateway_message_requires_issue_context_for_numeric_tokens(self) -> None:
        response = self.client.post(
            "/gateway/message",
            json={
                "user_id": "user-1",
                "content": "请帮我 review 42 这个需求",
                "source": "manual",
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["intent"], "sleep_coding")
        self.assertIn("Provide an issue number", payload["message"])

    def test_create_review_endpoint(self) -> None:
        response = self.client.post(
            "/reviews",
            json={
                "source": {
                    "source_type": "local_code",
                    "local_path": ".",
                }
            },
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["source"]["source_type"], "local_code")

    def test_trigger_sleep_coding_review_endpoint(self) -> None:
        response = self.client.post("/tasks/sleep-coding/task-1/review")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["source"]["source_type"], "sleep_coding_task")
        self.assertEqual(payload["task_id"], "task-1")


if __name__ == "__main__":
    unittest.main()
