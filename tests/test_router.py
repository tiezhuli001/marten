import unittest

from app.graph.router import classify_intent


class IntentRouterTests(unittest.TestCase):
    def test_returns_stats_query_for_token_queries(self) -> None:
        self.assertEqual(classify_intent("帮我统计最近7天 token 消耗"), "stats_query")

    def test_returns_sleep_coding_for_code_requests(self) -> None:
        self.assertEqual(classify_intent("帮我修 bug 并发一个 pr"), "sleep_coding")

    def test_returns_general_for_other_questions(self) -> None:
        self.assertEqual(classify_intent("给我介绍一下这个项目"), "general")


if __name__ == "__main__":
    unittest.main()
