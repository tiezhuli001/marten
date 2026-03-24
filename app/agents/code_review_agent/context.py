from __future__ import annotations

from app.control.context import ContextAssemblyService
from app.agents.ralph import SleepCodingService
from app.agents.code_review_agent.target import ReviewTarget


class ReviewContextBuilder:
    _MAX_CHANGED_FILES = 12
    _MAX_DIFF_EXCERPT_CHARS_PER_FILE = 1600
    _MAX_DIFF_EVIDENCE_CHARS = 12000
    _MAX_WORKSPACE_CONTEXT_CHARS = 8000

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
            workspace_context = self._truncate_text(
                self.workspace_support.build_workspace_context(target),
                limit=self._MAX_WORKSPACE_CONTEXT_CHARS,
                label="workspace snapshot",
            )
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
        rendered_changes: list[str] = []
        diff_chars_used = 0
        remaining_files = 0
        for index, item in enumerate(file_changes):
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            diff_excerpt = item.get("diff_excerpt")
            if not isinstance(path, str) or not path.strip():
                continue
            if len(rendered_changes) >= self._MAX_CHANGED_FILES:
                remaining_files = sum(
                    1
                    for tail in file_changes[index:]
                    if isinstance(tail, dict)
                    and isinstance(tail.get("path"), str)
                    and str(tail.get("path")).strip()
                )
                break
            if isinstance(diff_excerpt, str) and diff_excerpt.strip():
                trimmed_excerpt = self._truncate_text(
                    diff_excerpt.strip(),
                    limit=self._MAX_DIFF_EXCERPT_CHARS_PER_FILE,
                    label=f"diff excerpt for {path.strip()}",
                )
                candidate = f"- {path.strip()}: {trimmed_excerpt}"
                separator = 1 if rendered_changes else 0
                if diff_chars_used + separator + len(candidate) > self._MAX_DIFF_EVIDENCE_CHARS:
                    remaining_files = sum(
                        1
                        for tail in file_changes[index:]
                        if isinstance(tail, dict)
                        and isinstance(tail.get("path"), str)
                        and str(tail.get("path")).strip()
                    )
                    break
                rendered_changes.append(candidate)
                diff_chars_used += separator + len(candidate)
            else:
                candidate = f"- {path.strip()}"
                separator = 1 if rendered_changes else 0
                if diff_chars_used + separator + len(candidate) > self._MAX_DIFF_EVIDENCE_CHARS:
                    remaining_files = sum(
                        1
                        for tail in file_changes[index:]
                        if isinstance(tail, dict)
                        and isinstance(tail.get("path"), str)
                        and str(tail.get("path")).strip()
                    )
                    break
                rendered_changes.append(candidate)
                diff_chars_used += separator + len(candidate)

        visible_changed_files = changed_files[: self._MAX_CHANGED_FILES]
        changed_files_rendered = "\n".join(f"- {path}" for path in visible_changed_files) if visible_changed_files else "- n/a"
        if len(changed_files) > len(visible_changed_files):
            changed_files_rendered += (
                f"\n- ... truncated {len(changed_files) - len(visible_changed_files)} additional changed files ..."
            )
        diff_evidence_rendered = "\n".join(rendered_changes) if rendered_changes else "- n/a"
        if remaining_files > 0:
            diff_evidence_rendered += f"\n- ... truncated {remaining_files} additional diff entries ..."
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
            f"{changed_files_rendered}\n"
            "Diff Evidence:\n"
            f"{diff_evidence_rendered}\n"
        )

    def _truncate_text(self, text: str, *, limit: int, label: str) -> str:
        normalized = text.strip()
        if len(normalized) <= limit:
            return normalized
        omitted = len(normalized) - limit
        return f"{normalized[:limit].rstrip()}\n... truncated {omitted} chars from {label} ..."
