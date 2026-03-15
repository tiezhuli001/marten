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


if __name__ == "__main__":
    unittest.main()
