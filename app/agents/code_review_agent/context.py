from __future__ import annotations

from app.control.context import ContextAssemblyService
from app.agents.ralph import SleepCodingService
from app.agents.code_review_agent.target import ReviewTarget


class ReviewContextBuilder:
    def __init__(
        self,
        context: ContextAssemblyService,
        sleep_coding: SleepCodingService,
        workspace_support: object,
    ) -> None:
        self.context = context
        self.sleep_coding = sleep_coding
        self.workspace_support = workspace_support

    def build_context(
        self,
        target: ReviewTarget,
        run_session_id: str | None = None,
    ) -> str:
        if not target.task_id:
            raise ValueError("MVP review only supports sleep_coding_task sources")
        task = self.sleep_coding.get_task(target.task_id)
        base_context = self._build_task_evidence_context(task)
        if target.workspace_path:
            workspace_context = self.workspace_support.build_workspace_context(target)
            base_context = (
                f"{base_context}\n"
                "Workspace Snapshot:\n"
                f"{workspace_context}"
            )
        return self.context.build_agent_input(
            session_id=run_session_id,
            current_input=base_context,
            heading="Current Review Context",
        )

    def _build_task_evidence_context(self, task) -> str:
        latest_commit_message = "n/a"
        file_changes = list(task.git_execution.file_changes)
        changed_files = list(task.git_execution.changed_files)
        for event in reversed(task.events):
            if event.event_type != "coding_draft_generated":
                continue
            commit_message = event.payload.get("commit_message")
            if isinstance(commit_message, str) and commit_message.strip():
                latest_commit_message = commit_message.strip()
            break
        rendered_changes = []
        for item in file_changes:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            diff_excerpt = item.get("diff_excerpt")
            if not isinstance(path, str) or not path.strip():
                continue
            if isinstance(diff_excerpt, str) and diff_excerpt.strip():
                rendered_changes.append(f"- {path.strip()}: {diff_excerpt.strip()}")
            else:
                rendered_changes.append(f"- {path.strip()}")
        return (
            f"Task ID: {task.task_id}\n"
            f"Repo: {task.repo}\n"
            f"Issue Title: {task.issue.title}\n"
            f"Issue Body: {task.issue.body or 'n/a'}\n"
            f"PR: {task.pull_request.html_url if task.pull_request else 'n/a'}\n"
            f"Head Branch: {task.head_branch}\n"
            f"Validation: {task.validation.status}\n"
            f"Validation Workspace: {task.validation.workspace_path or 'n/a'}\n"
            f"Artifact: {task.git_execution.artifact_path or 'n/a'}\n"
            f"Plan: {task.plan.summary if task.plan else 'n/a'}\n"
            f"Commit Summary: {latest_commit_message}\n"
            f"Diff Summary: {task.git_execution.diff_summary or 'n/a'}\n"
            "Changed Files Evidence:\n"
            f"{chr(10).join(f'- {path}' for path in changed_files) if changed_files else '- n/a'}\n"
            "Diff Evidence:\n"
            f"{chr(10).join(rendered_changes) if rendered_changes else '- n/a'}\n"
        )
