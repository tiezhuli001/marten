from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Callable, TypeVar

T = TypeVar("T")


class BackgroundJobService:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="youmeng-bg",
        )
        self._active_keys: set[str] = set()
        self._lock = Lock()

    def submit_unique(
        self,
        key: str,
        fn: Callable[..., T],
        *args: object,
    ) -> bool:
        with self._lock:
            if key in self._active_keys:
                return False
            self._active_keys.add(key)
        future = self._executor.submit(fn, *args)
        future.add_done_callback(lambda _: self._release(key))
        return True

    def active_keys(self) -> list[str]:
        with self._lock:
            return sorted(self._active_keys)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _release(self, key: str) -> None:
        with self._lock:
            self._active_keys.discard(key)


_DEFAULT_BACKGROUND_JOBS = BackgroundJobService()


def get_background_job_service() -> BackgroundJobService:
    return _DEFAULT_BACKGROUND_JOBS
