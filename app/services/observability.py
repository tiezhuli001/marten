from __future__ import annotations

import os
from contextlib import nullcontext
from typing import Any

from app.core.config import Settings

try:
    from langsmith import trace
except ImportError:  # pragma: no cover - dependency installation is deferred.
    trace = None


class LangSmithService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = bool(settings.langsmith_api_key and settings.langsmith_tracing)
        self._configure_environment()

    def _configure_environment(self) -> None:
        if not self.enabled:
            return
        os.environ["LANGSMITH_API_KEY"] = self.settings.langsmith_api_key or ""
        os.environ["LANGSMITH_PROJECT"] = self.settings.langsmith_project
        os.environ["LANGSMITH_TRACING"] = "true"

    def request_trace(
        self,
        *,
        request_id: str,
        run_id: str,
        user_id: str,
    ) -> Any:
        if not self.enabled or trace is None:
            return nullcontext()
        return trace(
            name="gateway_request",
            run_type="chain",
            project_name=self.settings.langsmith_project,
            metadata={
                "request_id": request_id,
                "run_id": run_id,
                "user_id": user_id,
            },
        )
