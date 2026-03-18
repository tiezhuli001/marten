from __future__ import annotations

import sys
import unittest
from pathlib import Path


SMOKE_TESTS = (
    "tests.test_sleep_coding.SleepCodingServiceTests.test_falls_back_to_heuristic_plan_and_execution_when_llm_fails",
    "tests.test_sleep_coding.SleepCodingServiceTests.test_uses_configured_validation_command",
    "tests.test_review.ReviewServiceTests.test_review_skill_falls_back_to_dry_run_when_llm_call_fails",
)


def main() -> int:
    project_root = Path.cwd()
    sys.path.insert(0, str(project_root))
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(list(SMOKE_TESTS))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
