from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


SMOKE_TESTS = (
    "tests.test_sleep_coding.SleepCodingServiceTests.test_start_task_generates_plan_and_waits_for_confirmation",
    "tests.test_sleep_coding.SleepCodingServiceTests.test_uses_configured_validation_command",
    "tests.test_review.ReviewServiceTests.test_review_skill_runs_through_builtin_runtime_only",
)


def main() -> int:
    project_root = Path.cwd()
    sys.path.insert(0, str(project_root))
    with tempfile.TemporaryDirectory(prefix="marten-validation-") as temp_dir:
        isolated = Path(temp_dir)
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["MINIMAX_API_KEY"] = ""
        os.environ["GITHUB_TOKEN"] = ""
        os.environ["MODELS_CONFIG_PATH"] = str(isolated / "models.json")
        os.environ["MCP_CONFIG_PATH"] = str(isolated / "mcp.json")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(list(SMOKE_TESTS))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
