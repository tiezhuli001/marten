from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib import error, request

from app.channel.endpoints import ChannelEndpointRegistry
from app.core.config import Settings


@dataclass
class ChannelNotificationResult:
    provider: str
    delivered: bool
    is_dry_run: bool
    endpoint_id: str | None = None


class ChannelNotificationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.resolved_channel_provider
        self.webhook_url = None if settings.app_env == "test" else settings.channel_webhook_url
        self.endpoints = ChannelEndpointRegistry(settings)

    def notify(
        self,
        title: str,
        lines: list[str],
        endpoint_id: str | None = None,
    ) -> ChannelNotificationResult:
        endpoint = self.endpoints.get_endpoint(endpoint_id) if endpoint_id else None
        provider = endpoint.provider if endpoint is not None else self.provider
        webhook_url = None if self.settings.app_env == "test" else (
            endpoint.webhook_url if endpoint is not None and endpoint.webhook_url else self.webhook_url
        )
        if not webhook_url:
            return ChannelNotificationResult(
                provider=provider,
                delivered=False,
                is_dry_run=True,
                endpoint_id=endpoint.endpoint_id if endpoint is not None else endpoint_id,
            )

        payload = self._build_payload(title, lines, provider)
        http_request = request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=15):
                return ChannelNotificationResult(
                    provider=provider,
                    delivered=True,
                    is_dry_run=False,
                    endpoint_id=endpoint.endpoint_id if endpoint is not None else endpoint_id,
                )
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"Channel notification failed: {exc.code} {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Channel notification is unreachable: {exc.reason}") from exc

    def _build_payload(
        self,
        title: str,
        lines: list[str],
        provider: str | None = None,
    ) -> dict[str, object]:
        active_provider = provider or self.provider
        if active_provider == "feishu":
            return self._build_feishu_card_payload(title, lines)
        message = title + "\n" + "\n".join(lines)
        return {"text": message}

    def _build_feishu_card_payload(
        self,
        title: str,
        lines: list[str],
    ) -> dict[str, object]:
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True, "enable_forward": True},
                "header": {
                    "template": self._feishu_header_template(title),
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": self._build_feishu_card_elements(title, lines),
            },
        }

    def _build_feishu_card_elements(
        self,
        title: str,
        lines: list[str],
    ) -> list[dict[str, object]]:
        elements: list[dict[str, object]] = []
        overview_lines, sections = self._partition_feishu_lines(lines)
        if overview_lines:
            elements.append(
                {
                    "tag": "markdown",
                    "content": self._render_overview_block(title, overview_lines),
                }
            )
        for heading, body_lines in sections:
            if elements:
                elements.append({"tag": "hr"})
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"**{heading}**",
                }
            )
            if body_lines and all(line.startswith("|") for line in body_lines):
                elements.extend(self._render_feishu_table_elements(heading, body_lines))
            else:
                elements.append(
                    {
                        "tag": "markdown",
                        "content": "\n".join(self._format_feishu_line(line) for line in body_lines),
                    }
                )
        if not elements:
            elements.append({"tag": "markdown", "content": "No details provided."})
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "Youmeng Gateway · Sleep Coding MVP",
                    }
                ],
            }
        )
        return elements

    def _partition_feishu_lines(
        self,
        lines: list[str],
    ) -> tuple[list[str], list[tuple[str, list[str]]]]:
        overview: list[str] = []
        sections: list[tuple[str, list[str]]] = []
        current_heading: str | None = None
        current_body: list[str] = []
        pending_table: list[str] = []
        for raw_line in lines:
            line = raw_line.rstrip()
            if not line:
                if pending_table:
                    current_body.extend(pending_table)
                    pending_table = []
                continue
            if line.startswith("|"):
                pending_table.append(line)
                continue
            if pending_table:
                current_body.extend(pending_table)
                pending_table = []
            if self._is_section_heading(line):
                if current_heading is not None or current_body:
                    sections.append((current_heading or "详情", current_body))
                current_heading = line.rstrip(":")
                current_body = []
                continue
            if current_heading is None:
                overview.append(line)
            else:
                current_body.append(line)
        if pending_table:
            current_body.extend(pending_table)
        if current_heading is not None or current_body:
            sections.append((current_heading or "详情", current_body))
        return overview, sections

    def _render_overview_block(self, title: str, overview_lines: list[str]) -> str:
        label = "执行概览"
        if "任务完成" in title:
            label = "交付概览"
        elif "任务开始" in title or "Started Issue" in title:
            label = "执行开始"
        elif "issue prepared" in title.lower():
            label = "需求已接收"
        return "\n".join(
            [f"**{label}**", *[self._format_feishu_line(line) for line in overview_lines]]
        )

    def _render_feishu_table_elements(
        self,
        heading: str,
        table_lines: list[str],
    ) -> list[dict[str, object]]:
        headers, rows = self._parse_markdown_table(table_lines)
        if not headers or not rows:
            return [
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": "\n".join(table_lines),
                    },
                }
            ]
        if "Token" in heading:
            return self._render_token_table_elements(headers, rows)
        return [
            {
                "tag": "markdown",
                "content": "\n".join(self._format_table_row(headers, row) for row in rows),
            }
        ]

    def _parse_markdown_table(
        self,
        table_lines: list[str],
    ) -> tuple[list[str], list[list[str]]]:
        rows: list[list[str]] = []
        for line in table_lines:
            stripped = line.strip()
            if not stripped.startswith("|") or stripped.count("|") < 2:
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(cell.replace("-", "").replace(":", "").strip() == "" for cell in cells):
                continue
            rows.append(cells)
        if len(rows) < 2:
            return [], []
        return rows[0], rows[1:]

    def _render_token_table_elements(
        self,
        headers: list[str],
        rows: list[list[str]],
    ) -> list[dict[str, object]]:
        rendered_rows = [
            {
                "tag": "markdown",
                "content": self._format_table_row(headers, row),
            }
            for row in rows
        ]
        return rendered_rows

    def _format_table_row(
        self,
        headers: list[str],
        row: list[str],
    ) -> str:
        pairs = []
        for index, cell in enumerate(row):
            header = headers[index] if index < len(headers) else f"列{index + 1}"
            if index == 0:
                pairs.append(f"**{cell}**")
            else:
                pairs.append(f"{header}: {cell}")
        return "- " + " · ".join(pairs)

    def _is_section_heading(self, line: str) -> bool:
        return line.endswith(":") or line.startswith(("一、", "二、", "三、", "四、"))

    def _format_feishu_line(self, line: str) -> str:
        if re.match(r"^\d+\.\s", line) or line.startswith(("- ", "* ")):
            return line
        if ": " not in line:
            return f"- {line}"
        key, value = line.split(": ", 1)
        stripped_value = value.strip()
        if stripped_value.startswith("http://") or stripped_value.startswith("https://"):
            return f"**{key}**: [{stripped_value}]({stripped_value})"
        return f"**{key}**: {stripped_value}"

    def _feishu_header_template(self, title: str) -> str:
        normalized = title.lower()
        if "任务完成" in title or "approved" in normalized:
            return "green"
        if "manual review required" in normalized or "failed" in normalized:
            return "red"
        if "任务开始" in title or "started issue" in normalized:
            return "orange"
        return "blue"
