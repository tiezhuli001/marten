from __future__ import annotations

from app.control.context import ContextAssemblyService
from app.models.schemas import ReviewSource
from app.agents.ralph import SleepCodingService


class ReviewContextBuilder:
    def __init__(
        self,
        context: ContextAssemblyService,
        sleep_coding: SleepCodingService,
        source_support: object,
    ) -> None:
        self.context = context
        self.sleep_coding = sleep_coding
        self.source_support = source_support

    def build_context(
        self,
        source: ReviewSource,
        run_session_id: str | None = None,
    ) -> str:
        base_context: str
        if source.source_type == "sleep_coding_task" and source.task_id:
            task = self.sleep_coding.get_task(source.task_id)
            latest_commit_message = "n/a"
            file_changes: list[str] = []
            for event in reversed(task.events):
                if event.event_type != "coding_draft_generated":
                    continue
                commit_message = event.payload.get("commit_message")
                if isinstance(commit_message, str) and commit_message.strip():
                    latest_commit_message = commit_message.strip()
                raw_file_changes = event.payload.get("file_changes")
                if isinstance(raw_file_changes, list):
                    for item in raw_file_changes:
                        if not isinstance(item, dict):
                            continue
                        path = item.get("path")
                        description = item.get("description")
                        if isinstance(path, str) and path.strip():
                            if isinstance(description, str) and description.strip():
                                file_changes.append(f"- {path.strip()}: {description.strip()}")
                            else:
                                file_changes.append(f"- {path.strip()}")
                break
            base_context = (
                f"Task ID: {task.task_id}\n"
                f"Repo: {task.repo}\n"
                f"Issue Title: {task.issue.title}\n"
                f"Issue Body: {task.issue.body or 'n/a'}\n"
                f"PR: {task.pull_request.html_url if task.pull_request else 'n/a'}\n"
                f"Head Branch: {task.head_branch}\n"
                f"Validation: {task.validation.status}\n"
                f"Artifact: {task.git_execution.artifact_path or 'n/a'}\n"
                f"Plan: {task.plan.summary if task.plan else 'n/a'}\n"
                f"Commit Summary: {latest_commit_message}\n"
                "File Changes:\n"
                f"{chr(10).join(file_changes) if file_changes else '- n/a'}\n"
            )
        elif source.source_type == "local_code":
            base_context = self.source_support.build_local_code_context(source)
        else:
            base_context = (
                f"Source URL: {source.url or 'n/a'}\n"
                f"Repo: {source.repo or 'n/a'}\n"
                f"PR Number: {source.pr_number or 'n/a'}\n"
                f"MR Number: {source.mr_number or 'n/a'}\n"
                f"Project Path: {source.project_path or 'n/a'}\n"
            )
        return self.context.build_agent_input(
            session_id=run_session_id,
            current_input=base_context,
            heading="Current Review Context",
        )
