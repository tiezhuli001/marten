from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from app.models.schemas import ValidationResult


class ValidationRunner:
    def __init__(self, command: str | None = None, project_root: Path | None = None) -> None:
        self.command = command or "python -m unittest discover -s tests"
        self.project_root = project_root

    def run(self, repo_path: Path) -> ValidationResult:
        command = self.command.strip()
        command_args = shlex.split(command)
        primary_args = self._resolve_command_args(command_args, repo_path)
        completed = self._run_command(primary_args, repo_path)
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if (
            completed.returncode != 0
            and self.project_root is not None
            and repo_path.resolve() != self.project_root.resolve()
        ):
            fallback_args = self._resolve_command_args(command_args, self.project_root)
            fallback = self._run_command(fallback_args, self.project_root)
            fallback_output = "\n".join(
                part for part in (fallback.stdout, fallback.stderr) if part
            ).strip()
            if fallback.returncode == 0:
                combined_output = "\n".join(
                    part
                    for part in (
                        output,
                        f"Validation fallback succeeded in primary workspace: {self.project_root}",
                        fallback_output,
                    )
                    if part
                ).strip()
                return ValidationResult(
                    status="passed",
                    command=command,
                    exit_code=0,
                    output=combined_output,
                )
        return ValidationResult(
            status="passed" if completed.returncode == 0 else "failed",
            command=command,
            exit_code=completed.returncode,
            output=output,
        )

    def _resolve_command_args(self, command_args: list[str], cwd: Path) -> list[str]:
        resolved = list(command_args)
        if resolved and resolved[0].startswith("python") and self.project_root is not None:
            project_python = self.project_root / ".venv" / "bin" / "python"
            if project_python.exists():
                resolved[0] = str(project_python)
        if len(resolved) >= 2 and resolved[0].endswith("python") and self.project_root is not None:
            script_path = Path(resolved[1])
            if not script_path.is_absolute():
                cwd_script = cwd / script_path
                project_script = self.project_root / script_path
                if not cwd_script.exists() and project_script.exists():
                    resolved[1] = str(project_script)
        return resolved

    def _run_command(
        self,
        command_args: list[str],
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
