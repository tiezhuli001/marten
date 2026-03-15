import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.ledger.service import TokenLedgerService


def build_settings(database_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        langsmith_tracing=False,
    )


class TokenLedgerTests(unittest.TestCase):
    def test_record_request_persists_minimal_rows(self) -> None:
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
            )

            self.assertEqual(usage.total_tokens, 0)
            self.assertTrue(service.database_path.exists())

    def test_get_usage_summary_reports_counts(self) -> None:
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
            )

            summary = service.get_usage_summary("最近7天 token")

            self.assertIn("Period=7d", summary)
            self.assertIn("requests=1", summary)


if __name__ == "__main__":
    unittest.main()
