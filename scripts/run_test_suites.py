from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.testing.suites import build_unittest_command, get_test_suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run layered Marten test suites.")
    parser.add_argument(
        "suite",
        nargs="?",
        default="quick",
        choices=("quick", "fast", "default", "regression", "full", "manual", "extended", "live"),
        help="Suite to run. Defaults to quick.",
    )
    args = parser.parse_args(argv)
    suite = get_test_suite(args.suite)
    command = build_unittest_command(suite.name)
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
