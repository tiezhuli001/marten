import unittest

from fastapi.testclient import TestClient

from app.main import app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

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


if __name__ == "__main__":
    unittest.main()
