from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path

from app.core.config import Settings
from app.models.schemas import GitExecutionResult, SleepCodingFileChange
from app.runtime.mcp import MCPClient, MCPToolCall, build_default_mcp_client, get_mcp_server_definition


class GitWorkspaceService:
    _GIT_TIMEOUT_SECONDS = 120

    def __init__(self, settings: Settings, mcp_client: MCPClient | None = None) -> None:
        self.settings = settings
        self.repo_path = settings.project_root
        self.worktree_root = settings.resolved_sleep_coding_worktree_root
        self.enable_git_commit = settings.resolved_sleep_coding_enable_git_commit
        self.enable_git_push = settings.resolved_sleep_coding_enable_git_push
        self.git_remote_name = settings.resolved_git_remote_name
        self.github_server = settings.mcp_github_server_name
        self.github_repo = settings.resolved_github_repository
        self.mcp_client = mcp_client
        self._pending_messages: dict[str, str] = {}
        self._pending_files: dict[str, list[str]] = {}

    def prepare_worktree(self, branch: str) -> GitExecutionResult:
        worktree_path = self.worktree_root / self._sanitize_branch(branch)
        self._ensure_remote_branch(branch)
        if not self.enable_git_commit:
            return GitExecutionResult(
                status="prepared",
                worktree_path=str(worktree_path),
                output="Remote branch prepared via MCP. Local git worktree is in dry-run mode.",
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
        self._pending_messages[branch] = message
        if self._supports_github_mcp_write():
            return GitExecutionResult(
                status="completed",
                worktree_path=str(worktree_path),
                output="Changes queued for MCP push.",
                is_dry_run=False,
            )
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
        artifact_markdown: str,
        file_changes: list[SleepCodingFileChange] | None = None,
    ) -> GitExecutionResult:
        worktree_path = self.worktree_root / self._sanitize_branch(branch)
        artifact_path = worktree_path / ".sleep_coding" / f"issue-{issue_number}.md"
        generated_changes = file_changes or []
        pending_files = [f".sleep_coding/issue-{issue_number}.md", *[change.path for change in generated_changes]]
        self._pending_files[branch] = pending_files
        artifact_content = (
            f"# Ralph Task\n\n"
            f"- task_id: {task_id}\n"
            f"- issue_number: {issue_number}\n"
            f"- branch: {branch}\n\n"
            f"{artifact_markdown.strip()}\n"
        )
        if not self.enable_git_commit:
            return GitExecutionResult(
                status="prepared",
                worktree_path=str(worktree_path),
                artifact_path=str(artifact_path),
                output=(
                    "Task artifact generation is in dry-run mode. "
                    f"Planned file changes: {len(generated_changes)}."
                ),
                is_dry_run=True,
            )

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(artifact_content, encoding="utf-8")
        for change in generated_changes:
            target_path = self._resolve_relative_path(worktree_path, change.path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(change.content, encoding="utf-8")
        return GitExecutionResult(
            status="prepared",
            worktree_path=str(worktree_path),
            artifact_path=str(artifact_path),
            output=(
                "Task artifact written to worktree. "
                f"Generated file changes: {len(generated_changes)}."
            ),
            is_dry_run=False,
        )

    def push_branch(self, branch: str) -> GitExecutionResult:
        worktree_path = self.worktree_root / self._sanitize_branch(branch)
        if self._supports_github_mcp_write():
            return self._push_branch_via_mcp(branch=branch, worktree_path=worktree_path)
        if not self.enable_git_push:
            return GitExecutionResult(
                status="skipped",
                worktree_path=str(worktree_path),
                push_remote=self.git_remote_name,
                output="Git push is disabled. Dry-run only.",
                is_dry_run=True,
            )

        push_target, sensitive_values = self._resolve_push_target(worktree_path)
        self._run_git(
            ["push", "-u", push_target, branch],
            cwd=worktree_path,
            sensitive_values=sensitive_values,
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
        sensitive_values: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.setdefault("GIT_TERMINAL_PROMPT", "0")
        environment.setdefault("GCM_INTERACTIVE", "never")
        environment.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=cwd or self.repo_path,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
                timeout=self._GIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            redacted_args = self._redact_sensitive_values(" ".join(args), sensitive_values)
            raise RuntimeError(
                f"Git command timed out after {self._GIT_TIMEOUT_SECONDS}s: git {redacted_args}"
            ) from exc
        if completed.returncode != 0:
            output = "\n".join(
                part for part in (completed.stdout, completed.stderr) if part
            ).strip()
            redacted_args = self._redact_sensitive_values(" ".join(args), sensitive_values)
            redacted_output = self._redact_sensitive_values(output, sensitive_values)
            raise RuntimeError(f"Git command failed: git {redacted_args}\n{redacted_output}")
        return completed

    def _push_branch_via_mcp(
        self,
        *,
        branch: str,
        worktree_path: Path,
    ) -> GitExecutionResult:
        files = self._collect_changed_files(worktree_path, branch=branch)
        if not files:
            return GitExecutionResult(
                status="skipped",
                worktree_path=str(worktree_path),
                output="No file changes detected; MCP push skipped.",
                is_dry_run=False,
            )
        message = self._pending_messages.get(branch) or f"Sleep coding: update {branch}"
        result = self._get_mcp_client().call_tool(
            MCPToolCall(
                server=self.github_server,
                tool="push_files",
                arguments={
                    "repo": self.github_repo,
                    "branch": branch,
                    "files": files,
                    "message": message,
                },
            )
        )
        payload = self._coerce_mapping(result.content)
        commit_sha = self._coerce_commit_sha(payload)
        output = payload.get("message")
        if not isinstance(output, str) or not output.strip():
            output = f"Pushed {len(files)} files via GitHub MCP."
        return GitExecutionResult(
            status="completed",
            worktree_path=str(worktree_path),
            commit_sha=commit_sha,
            push_remote="github-mcp",
            output=output,
            is_dry_run=False,
        )

    def _collect_changed_files(self, worktree_path: Path, *, branch: str) -> list[dict[str, str]]:
        status_output = self._run_git(
            ["status", "--short", "--untracked-files=all"],
            cwd=worktree_path,
        ).stdout.splitlines()
        changed_files: list[dict[str, str]] = []
        seen_paths: set[str] = set()
        for raw_line in status_output:
            if not raw_line.strip():
                continue
            path_text = raw_line[3:].strip()
            if " -> " in path_text:
                path_text = path_text.split(" -> ", 1)[1].strip()
            if not path_text:
                continue
            file_path = worktree_path / path_text
            if not file_path.exists() or file_path.is_dir():
                continue
            changed_files.append({"path": path_text, "content": file_path.read_text(encoding="utf-8")})
            seen_paths.add(path_text)
        for pending_path in self._pending_files.get(branch, []):
            if pending_path in seen_paths:
                continue
            file_path = worktree_path / pending_path
            if not file_path.exists() or file_path.is_dir():
                continue
            changed_files.append(
                {
                    "path": pending_path,
                    "content": file_path.read_text(encoding="utf-8"),
                }
            )
            seen_paths.add(pending_path)
        return changed_files

    def _ensure_remote_branch(self, branch: str) -> None:
        if not self._supports_github_mcp_write():
            return
        try:
            self._get_mcp_client().call_tool(
                MCPToolCall(
                    server=self.github_server,
                    tool="create_branch",
                    arguments={
                        "repo": self.github_repo,
                        "branch": branch,
                    },
                )
            )
        except Exception as exc:
            message = str(exc).lower()
            if "already exists" in message or "reference already exists" in message:
                return
            raise

    def _supports_github_mcp_write(self) -> bool:
        if not self.enable_git_commit or not self.enable_git_push:
            return False
        client = self._get_mcp_client()
        return (
            self.github_server in client.available_servers()
            and client.has_tool(self.github_server, "create_branch")
            and client.has_tool(self.github_server, "push_files")
        )

    def _get_mcp_client(self) -> MCPClient:
        if self.mcp_client is None:
            self.mcp_client = build_default_mcp_client(self.settings)
        return self.mcp_client

    def _coerce_mapping(self, content: object) -> dict[str, object]:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    return item
        return {}

    def _coerce_commit_sha(self, payload: dict[str, object]) -> str | None:
        for key in ("sha", "commitSha", "commit_sha"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        commit = payload.get("commit")
        if isinstance(commit, dict):
            sha = commit.get("sha")
            if isinstance(sha, str) and sha.strip():
                return sha.strip()
        return None

    def _resolve_push_target(self, worktree_path: Path) -> tuple[str, list[str]]:
        remote_url = self._run_git(
            ["remote", "get-url", self.git_remote_name],
            cwd=worktree_path,
        ).stdout.strip()
        token = self._github_pat_from_mcp_config()
        https_url = self._normalize_https_remote(remote_url)
        if not token or https_url is None:
            return self.git_remote_name, []
        authenticated_url = https_url.replace(
            "https://",
            f"https://x-access-token:{token}@",
            1,
        )
        return authenticated_url, [token]

    def _normalize_https_remote(self, remote_url: str) -> str | None:
        if remote_url.startswith("https://github.com/"):
            return remote_url
        if remote_url.startswith("git@github.com:"):
            return f"https://github.com/{remote_url.removeprefix('git@github.com:')}"
        if remote_url.startswith("ssh://git@github.com/"):
            return f"https://github.com/{remote_url.removeprefix('ssh://git@github.com/')}"
        return None

    def _github_pat_from_mcp_config(self) -> str | None:
        definition = get_mcp_server_definition(self.settings, self.github_server)
        if definition is None:
            return None
        return definition.env.get("GITHUB_PERSONAL_ACCESS_TOKEN") or definition.env.get("GITHUB_TOKEN")

    def _redact_sensitive_values(
        self,
        text: str,
        sensitive_values: list[str] | None,
    ) -> str:
        redacted = text
        for value in sensitive_values or []:
            if value:
                redacted = redacted.replace(value, "***")
        return redacted

    def _sanitize_branch(self, branch: str) -> str:
        return branch.replace("/", "__")

    def _resolve_relative_path(self, worktree_path: Path, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError(f"Generated file path must be relative: {relative_path}")
        resolved = (worktree_path / candidate).resolve()
        worktree_root = worktree_path.resolve()
        if worktree_root == resolved or worktree_root in resolved.parents:
            return resolved
        raise ValueError(f"Generated file path escapes worktree: {relative_path}")
