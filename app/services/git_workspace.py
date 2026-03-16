from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.config import Settings
from app.models.schemas import GitExecutionResult


class GitWorkspaceService:
    def __init__(self, settings: Settings) -> None:
        self.repo_path = settings.project_root
        self.worktree_root = settings.resolved_sleep_coding_worktree_root
        self.enable_git_commit = settings.sleep_coding_enable_git_commit
        self.enable_git_push = settings.sleep_coding_enable_git_push
        self.git_remote_name = settings.git_remote_name

    def prepare_worktree(self, branch: str) -> GitExecutionResult:
        worktree_path = self.worktree_root / self._sanitize_branch(branch)
        if not self.enable_git_commit:
            return GitExecutionResult(
                status="prepared",
                worktree_path=str(worktree_path),
                output="Git worktree preparation is in dry-run mode.",
                is_dry_run=True,
            )

        self.worktree_root.mkdir(parents=True, exist_ok=True)
        if worktree_path.exists():
            self._run_git(["worktree", "remove", "--force", str(worktree_path)])

        self._run_git(["worktree", "add", "-B", branch, str(worktree_path), "HEAD"])
        return GitExecutionResult(
            status="prepared",
            worktree_path=str(worktree_path),
            output="Git worktree prepared.",
            is_dry_run=False,
        )

    def commit_changes(
        self,
        branch: str,
        message: str,
    ) -> GitExecutionResult:
        worktree_path = self.worktree_root / self._sanitize_branch(branch)
        if not self.enable_git_commit:
            return GitExecutionResult(
                status="skipped",
                worktree_path=str(worktree_path),
                output="Git commit is disabled. Dry-run only.",
                is_dry_run=True,
            )

        status_output = self._run_git(
            ["status", "--short"],
            cwd=worktree_path,
        ).stdout.strip()
        if not status_output:
            return GitExecutionResult(
                status="skipped",
                worktree_path=str(worktree_path),
                output="No file changes detected; commit skipped.",
                is_dry_run=False,
            )

        self._run_git(["add", "-A"], cwd=worktree_path)
        self._run_git(["commit", "-m", message], cwd=worktree_path)
        sha = self._run_git(["rev-parse", "HEAD"], cwd=worktree_path).stdout.strip()
        return GitExecutionResult(
            status="completed",
            worktree_path=str(worktree_path),
            commit_sha=sha,
            output="Changes committed.",
            is_dry_run=False,
        )

    def write_task_artifact(
        self,
        branch: str,
        task_id: str,
        issue_number: int,
        plan_summary: str,
    ) -> GitExecutionResult:
        worktree_path = self.worktree_root / self._sanitize_branch(branch)
        artifact_path = worktree_path / ".sleep_coding" / f"issue-{issue_number}.md"
        artifact_content = (
            f"# Sleep Coding Task\n\n"
            f"- task_id: {task_id}\n"
            f"- issue_number: {issue_number}\n"
            f"- branch: {branch}\n"
            f"- plan_summary: {plan_summary}\n"
        )
        if not self.enable_git_commit:
            return GitExecutionResult(
                status="prepared",
                worktree_path=str(worktree_path),
                artifact_path=str(artifact_path),
                output="Task artifact generation is in dry-run mode.",
                is_dry_run=True,
            )

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(artifact_content, encoding="utf-8")
        return GitExecutionResult(
            status="prepared",
            worktree_path=str(worktree_path),
            artifact_path=str(artifact_path),
            output="Task artifact written to worktree.",
            is_dry_run=False,
        )

    def push_branch(self, branch: str) -> GitExecutionResult:
        worktree_path = self.worktree_root / self._sanitize_branch(branch)
        if not self.enable_git_push:
            return GitExecutionResult(
                status="skipped",
                worktree_path=str(worktree_path),
                push_remote=self.git_remote_name,
                output="Git push is disabled. Dry-run only.",
                is_dry_run=True,
            )

        self._run_git(
            ["push", "-u", self.git_remote_name, branch],
            cwd=worktree_path,
        )
        sha = self._run_git(["rev-parse", "HEAD"], cwd=worktree_path).stdout.strip()
        return GitExecutionResult(
            status="completed",
            worktree_path=str(worktree_path),
            commit_sha=sha,
            push_remote=self.git_remote_name,
            output="Branch pushed to remote.",
            is_dry_run=False,
        )

    def cleanup_worktree(self, branch: str) -> None:
        worktree_path = self.worktree_root / self._sanitize_branch(branch)
        if not self.enable_git_commit:
            return
        if worktree_path.exists():
            self._run_git(["worktree", "remove", "--force", str(worktree_path)])
        shutil.rmtree(worktree_path, ignore_errors=True)

    def _run_git(
        self,
        args: list[str],
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            output = "\n".join(
                part for part in (completed.stdout, completed.stderr) if part
            ).strip()
            raise RuntimeError(f"Git command failed: git {' '.join(args)}\n{output}")
        return completed

    def _sanitize_branch(self, branch: str) -> str:
        return branch.replace("/", "__")
