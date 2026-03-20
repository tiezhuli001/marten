import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.core.config import Settings
from app.ledger.service import TokenLedgerService
from app.models.schemas import TokenUsage


def build_settings(database_path: Path) -> Settings:
    models_config_path = database_path.parent / "models.json"
    if not models_config_path.exists():
        models_config_path.write_text("{}", encoding="utf-8")
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{database_path}",
        models_config_path=str(models_config_path),
        langsmith_tracing=False,
    )


class TokenLedgerTests(unittest.TestCase):
    def test_record_request_persists_usage_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "ledger.db"
            service = TokenLedgerService(build_settings(database_path))

            usage = service.record_request(
                request_id="req-1",
                run_id="run-1",
                user_id="user-1",
                source="manual",
                intent="general",
                content="hello",
                usage=TokenUsage(
                    prompt_tokens=11,
                    completion_tokens=7,
                    total_tokens=18,
                    cache_read_tokens=5,
                    reasoning_tokens=2,
                    message_count=3,
                    duration_seconds=1.5,
                    model_name="gpt-5-mini",
                    provider="openai",
                    cost_usd=0.12,
                    step_name="general_handler",
                ),
            )

            self.assertEqual(usage.total_tokens, 18)
            persisted_usage = service.get_request_usage("req-1")
            self.assertEqual(persisted_usage.model_name, "gpt-5-mini")
            self.assertEqual(persisted_usage.provider, "openai")
            self.assertEqual(persisted_usage.cost_usd, 0.12)
            self.assertEqual(persisted_usage.step_name, "general_handler")
            self.assertEqual(persisted_usage.cache_read_tokens, 5)
            self.assertEqual(persisted_usage.reasoning_tokens, 2)
            self.assertEqual(persisted_usage.message_count, 3)
            self.assertAlmostEqual(persisted_usage.duration_seconds, 1.5)

    def test_append_usage_accumulates_multiple_steps_for_same_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "ledger.db"
            service = TokenLedgerService(build_settings(database_path))
            service.record_request(
                request_id="req-1",
                run_id="run-1",
                user_id="user-1",
                source="manual",
                intent="sleep_coding",
                content="hello",
                usage=TokenUsage(
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                    message_count=2,
                    duration_seconds=1.0,
                    model_name="gpt-5-mini",
                    provider="openai",
                    cost_usd=0.01,
                    step_name="main_agent_issue_intake",
                ),
            )
            service.append_usage(
                request_id="req-1",
                run_id="run-2",
                usage=TokenUsage(
                    prompt_tokens=20,
                    completion_tokens=10,
                    total_tokens=30,
                    cache_read_tokens=8,
                    cache_write_tokens=3,
                    reasoning_tokens=4,
                    message_count=2,
                    duration_seconds=2.5,
                    model_name="MiniMax-M2.5",
                    provider="minimax",
                    cost_usd=0.02,
                    step_name="sleep_coding_plan",
                ),
            )

            usage = service.get_request_usage("req-1")

            self.assertEqual(usage.prompt_tokens, 30)
            self.assertEqual(usage.completion_tokens, 15)
            self.assertEqual(usage.total_tokens, 45)
            self.assertEqual(usage.cache_read_tokens, 8)
            self.assertEqual(usage.cache_write_tokens, 3)
            self.assertEqual(usage.reasoning_tokens, 4)
            self.assertEqual(usage.message_count, 4)
            self.assertAlmostEqual(usage.duration_seconds, 3.5)
            self.assertIsNone(usage.step_name)
            self.assertIsNone(usage.provider)
            self.assertIsNone(usage.model_name)

    def test_get_window_report_aggregates_recent_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "ledger.db"
            service = TokenLedgerService(build_settings(database_path))
            service.record_request(
                request_id="req-1",
                run_id="run-1",
                user_id="user-1",
                source="manual",
                intent="stats_query",
                content="最近7天 token",
                created_at="2026-03-16 09:00:00",
                usage=TokenUsage(
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                    cost_usd=0.2,
                    step_name="stats_query_handler",
                ),
            )
            service.record_request(
                request_id="req-2",
                run_id="run-2",
                user_id="user-2",
                source="manual",
                intent="sleep_coding",
                content="issue 42",
                created_at="2026-03-14 10:00:00",
                usage=TokenUsage(
                    prompt_tokens=20,
                    completion_tokens=10,
                    total_tokens=30,
                    cost_usd=0.4,
                    step_name="sleep_coding_handler",
                ),
            )
            service.record_request(
                request_id="req-old",
                run_id="run-old",
                user_id="user-3",
                source="manual",
                intent="general",
                content="old request",
                created_at="2026-02-01 08:00:00",
                usage=TokenUsage(
                    prompt_tokens=50,
                    completion_tokens=50,
                    total_tokens=100,
                    cost_usd=1.0,
                    step_name="general_handler",
                ),
            )

            report = service.get_window_report("7d", as_of=date(2026, 3, 16))

            self.assertEqual(report.window_summary.window, "7d")
            self.assertEqual(report.window_summary.request_count, 2)
            self.assertEqual(report.window_summary.total_tokens, 45)
            self.assertEqual(report.window_summary.estimated_cost_usd, 0.6)
            self.assertEqual(report.window_summary.by_intent[0].label, "sleep_coding")
            self.assertEqual(report.window_summary.by_step_name[0].label, "sleep_coding_handler")
            self.assertIn("top_intent=sleep_coding", report.summary_text)

    def test_generate_and_get_daily_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "ledger.db"
            service = TokenLedgerService(build_settings(database_path))
            service.record_request(
                request_id="req-1",
                run_id="run-1",
                user_id="user-1",
                source="manual",
                intent="general",
                content="review this pr",
                created_at="2026-03-15 10:00:00",
                usage=TokenUsage(
                    prompt_tokens=33,
                    completion_tokens=11,
                    total_tokens=44,
                    cost_usd=0.5,
                    step_name="review_writer",
                ),
            )
            service.record_request(
                request_id="req-2",
                run_id="run-2",
                user_id="user-2",
                source="manual",
                intent="general",
                content="review again",
                created_at="2026-03-15 11:00:00",
                usage=TokenUsage(
                    prompt_tokens=20,
                    completion_tokens=10,
                    total_tokens=30,
                    cost_usd=0.25,
                    step_name="review_writer",
                ),
            )

            generated = service.generate_daily_summary("2026-03-15")
            fetched = service.get_daily_summary("2026-03-15")

            self.assertEqual(generated.summary_date, "2026-03-15")
            self.assertEqual(fetched.request_count, 2)
            self.assertEqual(fetched.total_tokens, 74)
            self.assertEqual(fetched.top_intent, "general")
            self.assertEqual(fetched.top_step_name, "review_writer")
            self.assertIn("Daily token summary for 2026-03-15", fetched.summary_text)

    def test_generate_yesterday_summary_uses_previous_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "ledger.db"
            service = TokenLedgerService(build_settings(database_path))
            service.record_request(
                request_id="req-1",
                run_id="run-1",
                user_id="user-1",
                source="manual",
                intent="general",
                content="hello",
                created_at="2026-03-15 09:00:00",
                usage=TokenUsage(total_tokens=12),
            )

            summary = service.generate_yesterday_summary(today=date(2026, 3, 16))

            self.assertEqual(summary.summary_date, "2026-03-15")
            self.assertEqual(summary.total_tokens, 12)

    def test_get_usage_summary_routes_to_expected_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "ledger.db"
            service = TokenLedgerService(build_settings(database_path))
            service.record_request(
                request_id="req-1",
                run_id="run-1",
                user_id="user-1",
                source="manual",
                intent="stats_query",
                content="最近30天 token",
                created_at="2026-03-16 12:00:00",
                usage=TokenUsage(total_tokens=20, step_name="stats_query_handler"),
            )

            summary = service.get_usage_summary("最近30天 token")

            self.assertIn("Token report for 30d", summary)
            self.assertIn("total_tokens=20", summary)

    def test_schema_migration_rejects_unsupported_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "ledger.db"
            service = TokenLedgerService(build_settings(database_path))

            with self.assertRaisesRegex(ValueError, "Unsupported schema migration table"):
                with service._connect() as connection:
                    service._ensure_columns(connection, "bad_table", {"model_name": "TEXT"})

            with self.assertRaisesRegex(ValueError, "Unsupported schema migration columns"):
                with service._connect() as connection:
                    service._ensure_columns(
                        connection,
                        "token_usage_records",
                        {"bad_column": "TEXT"},
                    )


if __name__ == "__main__":
    unittest.main()
