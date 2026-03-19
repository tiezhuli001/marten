from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.models.schemas import (
    SleepCodingIssue,
    SleepCodingPlan,
    SleepCodingPullRequest,
    ValidationResult,
)
from app.runtime.mcp import MCPClient, MCPToolCall


@dataclass(frozen=True)
class GitHubCommentLike:
    html_url: str | None
    is_dry_run: bool


@dataclass(frozen=True)
class GitHubLabelLike:
    labels: list[str]
    is_dry_run: bool


class RalphGitHubBridge:
    def __init__(self, settings: Settings, mcp_client: MCPClient) -> None:
        self.settings = settings
        self.mcp_client = mcp_client

    def get_issue(
        self,
        repo: str,
        issue_number: int,
        title_override: str | None = None,
        body_override: str | None = None,
    ) -> SleepCodingIssue:
        server = self.require_github_server("get_issue")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="get_issue",
                arguments={"repo": repo, "issue_number": issue_number},
            )
        )
        payload = self.coerce_mapping(result.content)
        return SleepCodingIssue.model_validate(
            {
                "issue_number": payload.get("number", issue_number),
                "title": payload.get("title") or title_override or f"Sleep coding issue #{issue_number}",
                "body": payload.get("body") or body_override or "",
                "state": payload.get("state", "open"),
                "html_url": payload.get("html_url"),
                "labels": payload.get("labels", []),
                "is_dry_run": False,
            }
        )

    def create_issue_comment(
        self,
        repo: str,
        issue_number: int,
        body: str,
    ) -> GitHubCommentLike:
        server = self.require_github_server("create_issue_comment")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="create_issue_comment",
                arguments={"repo": repo, "issue_number": issue_number, "body": body},
            )
        )
        payload = self.coerce_mapping(result.content)
        return GitHubCommentLike(
            html_url=self.coerce_html_url(payload),
            is_dry_run=False,
        )

    def apply_labels(
        self,
        repo: str,
        issue_number: int,
        labels: list[str],
    ) -> GitHubLabelLike:
        if not labels:
            return GitHubLabelLike(labels=[], is_dry_run=False)
        server = self.require_github_server("apply_labels")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="apply_labels",
                arguments={"repo": repo, "issue_number": issue_number, "labels": labels},
            )
        )
        payload = self.coerce_mapping(result.content)
        resolved = payload.get("labels", labels)
        return GitHubLabelLike(
            labels=list(resolved) if isinstance(resolved, list) else labels,
            is_dry_run=False,
        )

    def create_pull_request(
        self,
        repo: str,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        validation: ValidationResult,
        head_branch: str,
        base_branch: str,
    ) -> SleepCodingPullRequest:
        title = f"[Ralph] #{issue.issue_number} {issue.title}"
        body = (
            "## Summary\n"
            f"{plan.summary}\n\n"
            "## Validation\n"
            f"- {validation.command}\n"
            f"- status: {validation.status}\n"
            f"- exit_code: {validation.exit_code}\n"
        )
        server = self.require_github_server("create_pull_request")
        for attempt in range(3):
            try:
                result = self.mcp_client.call_tool(
                    MCPToolCall(
                        server=server,
                        tool="create_pull_request",
                        arguments={
                            "repo": repo,
                            "title": title,
                            "body": body,
                            "head_branch": head_branch,
                            "base_branch": base_branch,
                        },
                    )
                )
                if result.is_error:
                    raise RuntimeError(self._coerce_error_message(result.content))
                payload = self.coerce_mapping(result.content)
                pr_url = self.coerce_html_url(payload)
                pr_number = payload.get("number")
                if pr_number is None and pr_url:
                    match = re.search(r"/pull/(?P<number>\d+)$", pr_url)
                    if match:
                        pr_number = int(match.group("number"))
                return SleepCodingPullRequest.model_validate(
                    {
                        "title": payload.get("title") or title,
                        "body": payload.get("body") or body,
                        "html_url": pr_url,
                        "pr_number": pr_number,
                        "state": payload.get("state", "open"),
                        "labels": [],
                        "is_dry_run": False,
                    }
                )
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
        raise RuntimeError("Failed to create pull request")

    def require_github_server(self, tool: str) -> str:
        server = self.settings.mcp_github_server_name
        if server not in self.mcp_client.available_servers():
            raise RuntimeError(
                f"GitHub MCP server `{server}` is not configured. Define it in {self.settings.resolved_mcp_config_path.name}."
            )
        if not self.mcp_client.has_tool(server, tool):
            raise RuntimeError(
                f"GitHub MCP server `{server}` does not expose required tool `{tool}`."
            )
        return server

    def coerce_mapping(self, content: object) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            text = content.strip()
            if not text:
                return {}
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                return loaded
            url_match = re.search(r"https://github\.com/\S+", text)
            if url_match:
                url = url_match.group(0).rstrip(").,]")
                return {"url": url, "html_url": url}
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    return item
                if isinstance(item, str):
                    candidate = self.coerce_mapping(item)
                    if candidate:
                        return candidate
        raise ValueError("MCP response did not contain a mapping payload")

    def coerce_html_url(self, payload: dict[str, Any]) -> str | None:
        for key in ("html_url", "url"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _coerce_error_message(self, content: object) -> str:
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [item.strip() for item in content if isinstance(item, str) and item.strip()]
            if parts:
                return "\n".join(parts)
        return "GitHub MCP tool returned an unknown error."
