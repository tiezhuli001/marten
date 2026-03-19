from __future__ import annotations

import json
from urllib import error, parse, request

from app.core.config import Settings
from app.models.github_results import GitHubCommentResult


class GitLabService:
    def __init__(self, settings: Settings) -> None:
        self.api_base = settings.gitlab_api_base.rstrip("/")
        self.token = settings.gitlab_token

    def create_merge_request_comment(
        self,
        project_path: str,
        mr_number: int,
        body: str,
    ) -> GitHubCommentResult:
        if not self.token:
            return GitHubCommentResult(
                html_url=f"https://gitlab.com/{project_path}/-/merge_requests/{mr_number}",
                is_dry_run=True,
            )

        project_id = parse.quote(project_path, safe="")
        payload = self._request_json(
            "POST",
            f"/projects/{project_id}/merge_requests/{mr_number}/notes",
            {"body": body},
        )
        note_id = payload.get("id")
        note_url = (
            f"https://gitlab.com/{project_path}/-/merge_requests/{mr_number}#note_{note_id}"
            if note_id
            else None
        )
        return GitHubCommentResult(
            html_url=note_url
            or payload.get("noteable_url")
            or f"https://gitlab.com/{project_path}/-/merge_requests/{mr_number}",
            is_dry_run=False,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        data = None
        headers = {"User-Agent": "marten"}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
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
            raise RuntimeError(f"GitLab API request failed: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"GitLab API is unreachable: {exc.reason}") from exc
