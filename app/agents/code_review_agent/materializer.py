from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import Settings
from app.models.schemas import ReviewSource
from app.agents.ralph import SleepCodingService


class ReviewMaterializationError(RuntimeError):
    pass


class ReviewSourceMaterializer:
    _GIT_TIMEOUT_SECONDS = 120

    def __init__(self, settings: Settings, sleep_coding: SleepCodingService) -> None:
        self.settings = settings
        self.sleep_coding = sleep_coding
        self.cache_root = settings.resolved_review_runs_dir / "sources"

    def materialize(self, source: ReviewSource) -> ReviewSource:
        if source.local_path:
            self._validate_local_checkout(
                local_path=Path(source.local_path).expanduser(),
                source_label=source.source_type,
                head_branch=source.head_branch,
            )
            return source
        if source.source_type == "sleep_coding_task" and source.task_id:
            return self._materialize_sleep_coding_task(source)
        if source.source_type == "github_pr" and source.repo and source.pr_number:
            return self._materialize_github_pr(source)
        if source.source_type == "gitlab_mr" and source.project_path and source.mr_number:
            return self._materialize_gitlab_mr(source)
        return source

    def _materialize_sleep_coding_task(self, source: ReviewSource) -> ReviewSource:
        task = self.sleep_coding.get_task(source.task_id)
        worktree_path = task.git_execution.worktree_path
        if not worktree_path or task.git_execution.is_dry_run:
            return source
        self._validate_local_checkout(
            local_path=Path(worktree_path),
            source_label=f"sleep_coding_task:{source.task_id}",
            head_branch=task.head_branch,
        )
        return source.model_copy(
            update={
                "local_path": worktree_path,
                "base_branch": task.base_branch,
                "head_branch": task.head_branch,
            }
        )

    def _materialize_github_pr(self, source: ReviewSource) -> ReviewSource:
        local_path = self.cache_root / "github" / source.repo.replace("/", "__") / f"pr-{source.pr_number}"
        remote_url = self._github_remote_url(source.repo)
        head_branch = f"review-pr-{source.pr_number}"
        self._prepare_remote_checkout(
            local_path=local_path,
            remote_url=remote_url,
            fetch_ref=f"pull/{source.pr_number}/head:{head_branch}",
            source_label=f"github_pr:{source.repo}#{source.pr_number}",
        )
        self._validate_local_checkout(
            local_path=local_path,
            source_label=f"github_pr:{source.repo}#{source.pr_number}",
            head_branch=head_branch,
        )
        return source.model_copy(
            update={
                "local_path": str(local_path),
                "base_branch": self._resolve_default_branch(local_path),
                "head_branch": head_branch,
            }
        )

    def _materialize_gitlab_mr(self, source: ReviewSource) -> ReviewSource:
        if not self.settings.gitlab_token:
            return source
        local_path = self.cache_root / "gitlab" / source.project_path.replace("/", "__") / f"mr-{source.mr_number}"
        remote_url = self._gitlab_remote_url(source)
        head_branch = f"review-mr-{source.mr_number}"
        self._prepare_remote_checkout(
            local_path=local_path,
            remote_url=remote_url,
            fetch_ref=f"refs/merge-requests/{source.mr_number}/head:{head_branch}",
            source_label=f"gitlab_mr:{source.project_path}!{source.mr_number}",
        )
        self._validate_local_checkout(
            local_path=local_path,
            source_label=f"gitlab_mr:{source.project_path}!{source.mr_number}",
            head_branch=head_branch,
        )
        return source.model_copy(
            update={
                "local_path": str(local_path),
                "base_branch": self._resolve_default_branch(local_path),
                "head_branch": head_branch,
            }
        )

    def _prepare_remote_checkout(
        self,
        *,
        local_path: Path,
        remote_url: str,
        fetch_ref: str,
        source_label: str,
    ) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not (local_path / ".git").exists():
                self._run_git(["clone", "--no-checkout", remote_url, str(local_path)], cwd=local_path.parent)
            self._run_git(["remote", "set-url", "origin", remote_url], cwd=local_path)
            self._run_git(["fetch", "--prune", "origin"], cwd=local_path)
            self._run_git(["fetch", "origin", fetch_ref], cwd=local_path)
        except RuntimeError as exc:
            raise ReviewMaterializationError(
                f"Failed to materialize {source_label} into local checkout.\n{exc}"
            ) from exc
        local_branch = fetch_ref.rsplit(":", 1)[-1]
        try:
            self._run_git(["checkout", "-B", local_branch, local_branch], cwd=local_path)
        except RuntimeError as exc:
            raise ReviewMaterializationError(
                f"Failed to checkout local branch `{local_branch}` for {source_label}.\n{exc}"
            ) from exc

    def _resolve_default_branch(self, local_path: Path) -> str:
        completed = self._run_git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=local_path)
        ref = completed.stdout.strip()
        if ref.startswith("origin/"):
            return ref.removeprefix("origin/")
        return "main"

    def _github_remote_url(self, repo: str) -> str:
        token = self._github_pat_from_mcp_config()
        if token:
            return f"https://x-access-token:{token}@github.com/{repo}.git"
        return f"https://github.com/{repo}.git"

    def _gitlab_remote_url(self, source: ReviewSource) -> str:
        parsed = urlparse(source.url or self.settings.gitlab_api_base)
        host = parsed.netloc or "gitlab.com"
        token = self.settings.gitlab_token
        if token:
            return f"https://oauth2:{token}@{host}/{source.project_path}.git"
        return f"https://{host}/{source.project_path}.git"

    def _github_pat_from_mcp_config(self) -> str | None:
        config_path = Path(self.settings.mcp_config_path)
        if not config_path.is_absolute():
            config_path = self.settings.project_root / config_path
        if not config_path.exists():
            return None
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        token = (
            payload.get("servers", {})
            .get(self.settings.mcp_github_server_name, {})
            .get("env", {})
            .get("GITHUB_PERSONAL_ACCESS_TOKEN")
        )
        if not isinstance(token, str) or not token or token.startswith("${"):
            return None
        return token

    def _run_git(self, args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.setdefault("GIT_TERMINAL_PROMPT", "0")
        environment.setdefault("GCM_INTERACTIVE", "never")
        environment.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            timeout=self._GIT_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
            raise RuntimeError(f"Git command failed: git {' '.join(args)}\n{output}")
        return completed

    def _validate_local_checkout(
        self,
        *,
        local_path: Path,
        source_label: str,
        head_branch: str | None,
    ) -> None:
        if not local_path.exists():
            raise ReviewMaterializationError(
                f"Local checkout for {source_label} does not exist: {local_path}"
            )
        if not (local_path / ".git").exists():
            raise ReviewMaterializationError(
                f"Local checkout for {source_label} is not a git repository: {local_path}"
            )
        if head_branch:
            try:
                self._run_git(["rev-parse", "--verify", head_branch], cwd=local_path)
            except RuntimeError as exc:
                raise ReviewMaterializationError(
                    f"Expected branch `{head_branch}` is unavailable in local checkout for {source_label}."
                ) from exc
