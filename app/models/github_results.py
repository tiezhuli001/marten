from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GitHubCommentResult:
    html_url: str | None
    is_dry_run: bool


@dataclass
class GitHubLabelResult:
    labels: list[str]
    is_dry_run: bool
