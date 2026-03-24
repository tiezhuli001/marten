from __future__ import annotations

import signal
import sys

from app.core.logging import setup_logging
from app.core.config import get_settings
from app.infra.scheduler import WorkerSchedulerService


def main() -> int:
    setup_logging()
    settings = get_settings()
    scheduler = WorkerSchedulerService(settings)

    def _handle_stop(_signum, _frame) -> None:  # noqa: ANN001
        scheduler.stop()

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    try:
        scheduler.run_forever()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
