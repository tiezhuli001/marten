from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import ReviewSource


REVIEW_SOURCE_TYPE = "sleep_coding_task"


@dataclass(frozen=True)
class ReviewTarget:
    task_id: str
    repo: str | None = None
    pr_number: int | None = None
    url: str | None = None
    workspace_path: str | None = None
    base_branch: str | None = None
    head_branch: str | None = None

    @classmethod
    def from_source(cls, source: ReviewSource) -> ReviewTarget:
        return cls(
            task_id=source.task_id or "",
            repo=source.repo,
            pr_number=source.pr_number,
            url=source.url,
            workspace_path=source.local_path,
            base_branch=source.base_branch,
            head_branch=source.head_branch,
        )

    def to_source(self) -> ReviewSource:
        return ReviewSource(
            source_type=REVIEW_SOURCE_TYPE,
            repo=self.repo,
            pr_number=self.pr_number,
            url=self.url,
            local_path=self.workspace_path,
            base_branch=self.base_branch,
            head_branch=self.head_branch,
            task_id=self.task_id,
        )
