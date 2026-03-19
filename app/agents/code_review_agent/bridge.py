from __future__ import annotations

from app.models.github_results import GitHubCommentResult
from app.models.schemas import ReviewRun, ReviewSource
from app.runtime.mcp import MCPClient, MCPToolCall
from app.agents.code_review_agent.gitlab import GitLabService


class ReviewCommentBridge:
    def __init__(
        self,
        github_server: str,
        mcp_client: MCPClient,
        gitlab: GitLabService,
        mcp_config_name: str,
    ) -> None:
        self.github_server = github_server
        self.mcp_client = mcp_client
        self.gitlab = gitlab
        self.mcp_config_name = mcp_config_name

    def write_comment(self, source: ReviewSource, content: str) -> GitHubCommentResult:
        if source.source_type == "github_pr" and source.repo and source.pr_number:
            return self.write_pr_review(source, event="COMMENT", body=content)
        if source.source_type == "sleep_coding_task" and source.repo and source.pr_number:
            return self.write_pr_review(source, event="COMMENT", body=content)
        if source.source_type == "gitlab_mr" and source.project_path and source.mr_number:
            return self.gitlab.create_merge_request_comment(
                project_path=source.project_path,
                mr_number=source.mr_number,
                body=content,
            )
        return GitHubCommentResult(html_url=source.url, is_dry_run=True)

    def write_pr_review(
        self,
        source: ReviewSource,
        *,
        event: str,
        body: str,
    ) -> GitHubCommentResult:
        server = self.require_github_server("pull_request_review_write")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="pull_request_review_write",
                arguments={
                    "repo": source.repo,
                    "pr_number": source.pr_number,
                    "method": "create",
                    "event": event,
                    "body": body,
                },
            )
        )
        payload = self.coerce_mapping(result.content)
        return GitHubCommentResult(
            html_url=self.coerce_html_url(payload) or source.url,
            is_dry_run=False,
        )

    def render_review_decision_comment(
        self,
        review: ReviewRun,
        action: str,
    ) -> str:
        decision_label = {
            "approve_review": "Approved",
            "request_changes": "Changes Requested",
            "cancel_review": "Cancelled",
        }.get(action, review.status)
        severity_parts = [
            f"{level}={review.severity_counts.get(level, 0)}"
            for level in ("P0", "P1", "P2", "P3")
            if review.severity_counts.get(level, 0) > 0
        ]
        findings = review.findings[:5]
        finding_lines = (
            [f"- [{item.severity}] {item.title}: {item.detail}" for item in findings]
            if findings
            else ["- No material findings."]
        )
        return "\n".join(
            [
                "## Ralph Review Decision",
                f"- Decision: {decision_label}",
                f"- Blocking: {'yes' if review.is_blocking else 'no'}",
                f"- Summary: {review.summary or 'n/a'}",
                f"- Severity: {', '.join(severity_parts) if severity_parts else 'No material findings'}",
                f"- Artifact: {review.artifact_path or 'n/a'}",
                f"- Review Link: {review.comment_url or 'n/a'}",
                "",
                "### Findings",
                *finding_lines,
                "",
                "### Token Usage",
                f"- Input Token: {review.token_usage.prompt_tokens:,}",
                f"- Output Token: {review.token_usage.completion_tokens:,}",
                f"- Total Token: {review.token_usage.total_tokens:,}",
                f"- Cache Read Token: {review.token_usage.cache_read_tokens:,}",
                f"- Cache Write Token: {review.token_usage.cache_write_tokens:,}",
                f"- Reasoning Token: {review.token_usage.reasoning_tokens:,}",
                f"- Messages: {review.token_usage.message_count:,}",
                f"- Duration: {review.token_usage.duration_seconds:.2f} seconds",
                f"- Cost: ${review.token_usage.cost_usd:.3f}",
            ]
        )

    def require_github_server(self, tool: str) -> str:
        if self.github_server not in self.mcp_client.available_servers():
            raise RuntimeError(
                f"GitHub MCP server `{self.github_server}` is not configured. Define it in {self.mcp_config_name}."
            )
        if not self.mcp_client.has_tool(self.github_server, tool):
            raise RuntimeError(
                f"GitHub MCP server `{self.github_server}` does not expose required tool `{tool}`."
            )
        return self.github_server

    def coerce_mapping(self, content: object) -> dict[str, object]:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    return item
        return {}

    def coerce_html_url(self, payload: dict[str, object]) -> str | None:
        for key in ("html_url", "url"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
