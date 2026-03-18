from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request

from app.core.config import Settings
from app.models.schemas import (
    GitHubIssueDraft,
    GitHubIssueResult,
    SleepCodingIssue,
    SleepCodingPlan,
    SleepCodingPullRequest,
    ValidationResult,
    WorkerDiscoveredIssue,
)


@dataclass
class GitHubCommentResult:
    html_url: str | None
    is_dry_run: bool


@dataclass
class GitHubLabelResult:
    labels: list[str]
    is_dry_run: bool


class GitHubService:
    def __init__(self, settings: Settings) -> None:
        self.api_base = settings.github_api_base.rstrip("/")
        self.token = settings.github_token

    def get_issue(
        self,
        repo: str,
        issue_number: int,
        title_override: str | None = None,
        body_override: str | None = None,
    ) -> SleepCodingIssue:
        if not self.token:
            return SleepCodingIssue(
                issue_number=issue_number,
                title=title_override or f"Sleep coding issue #{issue_number}",
                body=body_override
                or "GitHub dry-run mode. Configure GITHUB_TOKEN to read the real issue body.",
                html_url=f"https://github.com/{repo}/issues/{issue_number}",
                labels=[],
                creator_login="dry-run",
                is_dry_run=True,
            )

        payload = self._request_json("GET", f"/repos/{repo}/issues/{issue_number}")
        user = payload.get("user") or {}
        return SleepCodingIssue(
            issue_number=payload["number"],
            title=payload["title"],
            body=payload.get("body") or "",
            state=payload["state"],
            html_url=payload.get("html_url"),
            labels=[label["name"] for label in payload.get("labels", [])],
            creator_name=user.get("name"),
            creator_login=user.get("login"),
            is_dry_run=False,
        )

    def list_open_issues(
        self,
        repo: str,
        labels: list[str] | None = None,
        limit: int = 20,
    ) -> list[WorkerDiscoveredIssue]:
        if not self.token:
            return []
        query = f"/repos/{repo}/issues?state=open&per_page={limit}"
        if labels:
            query += f"&labels={','.join(labels)}"
        payload = self._request_json_list("GET", query)
        issues: list[WorkerDiscoveredIssue] = []
        for item in payload:
            if "pull_request" in item:
                continue
            issues.append(
                WorkerDiscoveredIssue(
                    issue_number=item["number"],
                    title=item["title"],
                    body=item.get("body") or "",
                    state=item.get("state", "open"),
                    html_url=item.get("html_url"),
                    labels=[label["name"] for label in item.get("labels", [])],
                    is_dry_run=False,
                )
            )
        return issues

    def create_issue_comment(
        self,
        repo: str,
        issue_number: int,
        body: str,
    ) -> GitHubCommentResult:
        if not self.token:
            return GitHubCommentResult(
                html_url=f"https://github.com/{repo}/issues/{issue_number}",
                is_dry_run=True,
            )

        payload = self._request_json(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/comments",
            {"body": body},
        )
        return GitHubCommentResult(
            html_url=payload.get("html_url"),
            is_dry_run=False,
        )

    def create_issue(
        self,
        repo: str,
        draft: GitHubIssueDraft,
    ) -> GitHubIssueResult:
        if not self.token:
            return GitHubIssueResult(
                issue_number=None,
                title=draft.title,
                body=draft.body,
                html_url=f"https://github.com/{repo}/issues",
                labels=draft.labels,
                is_dry_run=True,
            )

        payload = self._request_json(
            "POST",
            f"/repos/{repo}/issues",
            {
                "title": draft.title,
                "body": draft.body,
                "labels": draft.labels,
            },
        )
        return GitHubIssueResult(
            issue_number=payload.get("number"),
            title=payload["title"],
            body=payload.get("body") or "",
            html_url=payload.get("html_url"),
            labels=[label["name"] for label in payload.get("labels", [])],
            is_dry_run=False,
        )

    def create_pull_request_comment(
        self,
        repo: str,
        pr_number: int,
        body: str,
    ) -> GitHubCommentResult:
        return self.create_issue_comment(repo=repo, issue_number=pr_number, body=body)

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
        body = self._build_pr_body(issue, plan, validation)
        if not self.token:
            return SleepCodingPullRequest(
                title=title,
                body=body,
                html_url=f"https://github.com/{repo}/compare/{base_branch}...{head_branch}",
                labels=[],
                is_dry_run=True,
            )

        payload = self._request_json(
            "POST",
            f"/repos/{repo}/pulls",
            {
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
        )
        return SleepCodingPullRequest(
            title=payload["title"],
            body=payload.get("body") or "",
            html_url=payload.get("html_url"),
            pr_number=payload.get("number"),
            state=payload.get("state", "open"),
            labels=[],
            is_dry_run=False,
        )

    def apply_labels(
        self,
        repo: str,
        issue_number: int,
        labels: list[str],
    ) -> GitHubLabelResult:
        if not labels:
            return GitHubLabelResult(labels=[], is_dry_run=not bool(self.token))
        if not self.token:
            return GitHubLabelResult(labels=labels, is_dry_run=True)

        payload = self._request_json(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/labels",
            {"labels": labels},
        )
        return GitHubLabelResult(
            labels=[label["name"] for label in payload],
            is_dry_run=False,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        response = self._request(method, path, payload)
        if not isinstance(response, dict):
            raise RuntimeError("GitHub API response was not an object")
        return response

    def _request_json_list(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        response = self._request(method, path, payload)
        if not isinstance(response, list):
            raise RuntimeError("GitHub API response was not a list")
        return response

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> object:
        data = None
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "youmeng-gateway",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        http_request = request.Request(
            f"{self.api_base}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"GitHub API request failed: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"GitHub API is unreachable: {exc.reason}") from exc

    def _build_pr_body(
        self,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        validation: ValidationResult,
    ) -> str:
        scope_lines = "\n".join(f"- {item}" for item in plan.scope) or "- No scope recorded"
        risk_lines = "\n".join(f"- {item}" for item in plan.risks) or "- No explicit risks"
        validation_lines = "\n".join(f"- {item}" for item in plan.validation)
        validation_result = (
            f"- Result: {validation.status}\n"
            f"- Command: `{validation.command}`\n"
            f"- Exit code: {validation.exit_code}"
        )
        return (
            f"Closes #{issue.issue_number}\n\n"
            f"## Plan Summary\n{plan.summary}\n\n"
            f"## Scope\n{scope_lines}\n\n"
            f"## Validation Plan\n{validation_lines}\n\n"
            f"## Validation Result\n{validation_result}\n\n"
            f"## Risks\n{risk_lines}"
        )
