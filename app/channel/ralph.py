from __future__ import annotations

from app.models.schemas import ValidationResult


class RalphNotificationBuilder:
    def build_plan_ready(
        self,
        *,
        issue_title: str,
        issue_number: int,
        repo: str,
        head_branch: str,
        issue_url: str | None,
        plan_summary: str,
        plan_preview: list[str],
    ) -> tuple[str, list[str]]:
        return (
            f"Ralph 执行计划：{issue_title}",
            [
                f"来源: Issue #{issue_number}",
                f"仓库: {repo}",
                f"分支: {head_branch}",
                f"Issue: {issue_url or 'n/a'}",
                "计划摘要:",
                plan_summary,
                "执行计划:",
                *plan_preview,
                "Ralph 已开始编码，完成后将自动提交 Pull Request 并进入 Code Review。",
            ],
        )

    def build_validation_failed(
        self,
        *,
        issue_number: int,
        repo: str,
        task_id: str,
        head_branch: str,
        validation: ValidationResult,
    ) -> tuple[str, list[str]]:
        return (
            f"[Ralph] Validation failed for Issue #{issue_number}",
            [
                f"Repo: {repo}",
                f"Task: {task_id}",
                f"Branch: {head_branch}",
                f"Status: failed",
                f"Exit code: {validation.exit_code}",
            ],
        )
