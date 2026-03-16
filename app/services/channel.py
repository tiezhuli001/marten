from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request

from app.core.config import Settings


@dataclass
class ChannelNotificationResult:
    provider: str
    delivered: bool
    is_dry_run: bool


class ChannelNotificationService:
    def __init__(self, settings: Settings) -> None:
        self.provider = settings.channel_provider
        self.webhook_url = settings.channel_webhook_url

    def notify(self, title: str, lines: list[str]) -> ChannelNotificationResult:
        message = title + "\n" + "\n".join(lines)
        if not self.webhook_url:
            return ChannelNotificationResult(
                provider=self.provider,
                delivered=False,
                is_dry_run=True,
            )

        payload = self._build_payload(message)
        http_request = request.Request(
            self.webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=15):
                return ChannelNotificationResult(
                    provider=self.provider,
                    delivered=True,
                    is_dry_run=False,
                )
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"Channel notification failed: {exc.code} {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Channel notification is unreachable: {exc.reason}") from exc

    def _build_payload(self, message: str) -> dict[str, object]:
        if self.provider == "feishu":
            return {
                "msg_type": "text",
                "content": {"text": message},
            }
        return {"text": message}
