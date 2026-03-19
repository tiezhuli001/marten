from __future__ import annotations

import sys
import unittest
from pathlib import Path


SMOKE_TESTS = (
    "tests.test_sleep_coding.SleepCodingServiceTests.test_start_task_generates_plan_and_waits_for_confirmation",
    "tests.test_sleep_coding.SleepCodingServiceTests.test_uses_configured_validation_command",
    "tests.test_review.ReviewServiceTests.test_summary_prefers_structured_summary_section",
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
