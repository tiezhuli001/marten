import unittest
from pathlib import Path

from app.core.config import Settings


class SettingsTests(unittest.TestCase):
    def test_resolved_data_dir_defaults_to_project_relative_path(self) -> None:
        settings = Settings()

        self.assertEqual(settings.resolved_data_dir, settings.project_root / "data")

    def test_resolved_database_path_defaults_to_project_relative_sqlite_file(self) -> None:
        settings = Settings(database_url="sqlite:///data/test.db")

        self.assertEqual(
            settings.resolved_database_path,
            settings.project_root / "data" / "test.db",
        )

    def test_resolved_database_path_preserves_absolute_sqlite_path(self) -> None:
        absolute_path = Path("/tmp/youmeng-gateway-test.db")
        settings = Settings(database_url=f"sqlite:///{absolute_path}")

        self.assertEqual(settings.resolved_database_path, absolute_path)


if __name__ == "__main__":
    unittest.main()
