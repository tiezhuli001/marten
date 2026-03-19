from __future__ import annotations

from app.ledger.service import TokenLedgerService
from app.models.schemas import ReviewRun, SleepCodingTask, TokenUsage


class DeliveryMessageBuilder:
    def __init__(self, ledger: TokenLedgerService) -> None:
        self.ledger = ledger

    def build_manual_handoff(self, task: SleepCodingTask, review: ReviewRun, *, blocking_reviews: int, max_repair_rounds: int) -> tuple[str, list[str]]:
        title = f"[Ralph] Manual review required for Issue #{task.issue_number}"
        lines = [
            f"Task: {task.task_id}",
            f"Repo: {task.repo}",
            f"PR: {task.pull_request.html_url if task.pull_request else 'n/a'}",
            f"Review: {review.comment_url or review.artifact_path or 'n/a'}",
            f"Blocking rounds: {blocking_reviews}/{max_repair_rounds}",
            "Status: changes_requested",
        ]
        return title, lines

    def build_review_feedback(
        self,
        task: SleepCodingTask,
        review: ReviewRun,
        *,
        review_round: int,
        max_repair_rounds: int,
    ) -> tuple[str, list[str]]:
        title = f"[Ralph] Review round {review_round} for Issue #{task.issue_number}"
        lines = [
            f"Task: {task.task_id}",
            f"Repo: {task.repo}",
            f"PR: {task.pull_request.html_url if task.pull_request else 'n/a'}",
            f"Blocking: {'yes' if review.is_blocking else 'no'}",
            f"Summary: {review.summary or 'n/a'}",
            f"Review artifact: {review.artifact_path or 'n/a'}",
            f"Rounds: {review_round}/{max_repair_rounds}",
        ]
        findings = review.findings[:5]
        if findings:
            lines.append("Findings:")
            lines.extend(f"- [{item.severity}] {item.title}" for item in findings)
        return title, lines

    def build_final_delivery(self, task: SleepCodingTask, review: ReviewRun | None = None) -> tuple[str, list[str]]:
        title = self._build_final_delivery_title(task)
        lines = [
            f"来源: Issue #{task.issue_number}",
            f"仓库: {task.repo}",
            f"分支: {task.head_branch}",
            f"{self._pull_request_label(task.pull_request.html_url if task.pull_request else None)}: {task.pull_request.html_url if task.pull_request else 'n/a'}",
            f"Code Review: {'approved' if review and not review.is_blocking else 'changes_requested' if review else 'n/a'}",
            f"Issue: {task.issue.html_url or 'n/a'}",
            f"Review: {review.comment_url or review.artifact_path or 'n/a'}" if review else "Review: n/a",
            *self._render_work_summary_lines(task, review),
            *self._render_token_usage_lines(task, review),
        ]
        return title, lines

    def _render_token_usage_lines(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None,
    ) -> list[str]:
        if task.kickoff_request_id:
            total_usage = self.ledger.get_request_usage(task.kickoff_request_id)
            plan_usage = self.ledger.get_request_usage(task.kickoff_request_id, ["sleep_coding_plan"])
            execution_usage = self.ledger.get_request_usage(
                task.kickoff_request_id,
                ["sleep_coding_execution"],
            )
            review_usage = (
                review.token_usage
                if review is not None and review.token_usage.total_tokens > 0
                else self.ledger.get_request_usage(task.kickoff_request_id, ["code_review"])
            )
        else:
            total_usage = task.token_usage
            plan_usage = TokenUsage()
            execution_usage = task.token_usage
            review_usage = review.token_usage if review is not None else TokenUsage()
        return [
            "三、Token 消耗统计",
            f"输入 Token: {total_usage.prompt_tokens:,}",
            f"输出 Token: {total_usage.completion_tokens:,}",
            f"总 Token: {total_usage.total_tokens:,}",
            f"缓存读取 Token: {total_usage.cache_read_tokens:,}",
            f"缓存写入 Token: {total_usage.cache_write_tokens:,}",
            f"推理 Token: {total_usage.reasoning_tokens:,}",
            f"消息数量: {total_usage.message_count:,}",
            f"处理时间: {total_usage.duration_seconds:.2f} 秒",
            f"总成本: ${total_usage.cost_usd:.3f}",
            "阶段分布:",
            self._render_stage_usage_line("Plan", plan_usage),
            self._render_stage_usage_line("Execution", execution_usage),
            self._render_stage_usage_line("Review", review_usage),
        ]

    def _render_stage_usage_line(
        self,
        stage: str,
        usage: TokenUsage,
    ) -> str:
        return (
            f"{stage}: 输入 {usage.prompt_tokens:,} · 输出 {usage.completion_tokens:,} · "
            f"总 {usage.total_tokens:,} · 成本 ${usage.cost_usd:.3f}"
        )

    def _build_final_delivery_title(self, task: SleepCodingTask) -> str:
        summary = self._latest_commit_message(task) or task.issue.title
        return f"Ralph 任务完成：{summary}"

    def _render_work_summary_lines(
        self,
        task: SleepCodingTask,
        review: ReviewRun | None,
    ) -> list[str]:
        lines = ["工作总结:"]
        lines.append(f"需求摘要: {task.issue.title}")
        if task.plan:
            lines.append(f"计划摘要: {task.plan.summary}")
        commit_message = self._latest_commit_message(task)
        if commit_message:
            lines.append(f"提交摘要: {commit_message}")
        file_changes = self._latest_file_changes(task)
        if file_changes:
            lines.extend(
                [
                    "一、修改文件清单",
                    f"本次共修改 {len(file_changes)} 个文件。",
                    "| 文件路径 | 变更类型 | 说明 |",
                    "|---------|---------|------|",
                ]
            )
            for item in file_changes:
                path = str(item.get("path") or "n/a")
                description = str(item.get("description") or "代码变更")
                lines.append(f"| {path} | {self._infer_change_type(path, description)} | {description} |")
            lines.extend(self._render_key_change_lines(file_changes))
        lines.extend(
            [
                "四、总结",
                *self._render_conclusion_lines(task, file_changes, review),
            ]
        )
        return lines

    def _latest_commit_message(self, task: SleepCodingTask) -> str | None:
        for event in reversed(task.events):
            if event.event_type != "coding_draft_generated":
                continue
            commit_message = event.payload.get("commit_message")
            if isinstance(commit_message, str) and commit_message.strip():
                return commit_message.strip()
        return None

    def _latest_file_changes(self, task: SleepCodingTask) -> list[dict[str, object]]:
        for event in reversed(task.events):
            if event.event_type != "coding_draft_generated":
                continue
            file_changes = event.payload.get("file_changes")
            if not isinstance(file_changes, list):
                continue
            normalized: list[dict[str, object]] = []
            for item in file_changes:
                if isinstance(item, dict):
                    normalized.append(item)
            if normalized:
                return normalized
            artifact_path = event.payload.get("artifact_path")
            if isinstance(artifact_path, str) and artifact_path.strip():
                return [
                    {
                        "path": artifact_path.strip(),
                        "description": "Ralph 任务产物与执行摘要",
                    }
                ]
        return []

    def _render_key_change_lines(self, file_changes: list[dict[str, object]]) -> list[str]:
        lines = ["二、关键变更说明"]
        for index, item in enumerate(file_changes[:5], start=1):
            path = str(item.get("path") or "n/a")
            description = str(item.get("description") or "代码变更")
            lines.append(f"{index}. {path} - {description}")
        return lines

    def _render_conclusion_lines(
        self,
        task: SleepCodingTask,
        file_changes: list[dict[str, object]],
        review: ReviewRun | None,
    ) -> list[str]:
        lines = [
            f"本次工作主要完成了 {max(len(file_changes), 1)} 项改动收口。",
        ]
        for index, item in enumerate(file_changes[:3], start=1):
            description = str(item.get("description") or "代码变更")
            lines.append(f"{index}. {description}")
        if review is not None:
            lines.append(
                f"Code Review 结果：{'已通过' if not review.is_blocking else '仍有阻塞项'}。"
            )
        lines.append("Ralph 已完成任务，请过目。")
        return lines

    def _infer_change_type(self, path: str, description: str) -> str:
        normalized = f"{path} {description}".lower()
        if any(keyword in normalized for keyword in ("新增", "create", "add", "new")):
            return "新增"
        if any(keyword in normalized for keyword in ("删除", "remove", "delete")):
            return "删除"
        return "修改"

    def _pull_request_label(self, url: str | None) -> str:
        if isinstance(url, str) and "/-/merge_requests/" in url:
            return "Merge Request"
        return "Pull Request"
