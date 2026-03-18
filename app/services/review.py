from __future__ import annotations

import json
import re
import shlex
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
from shutil import which
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.models.schemas import (
    ReviewActionRequest,
    ReviewFinding,
    ReviewRun,
    ReviewRunRequest,
    ReviewSkillOutput,
    ReviewSource,
    SleepCodingTaskActionRequest,
    TokenUsage,
)
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.mcp import MCPClient, MCPToolCall, build_default_mcp_client
from app.runtime.pricing import PricingRegistry
from app.runtime.token_counting import TokenCountingService
from app.services.github import GitHubCommentResult
from app.services.gitlab import GitLabService
from app.services.session_registry import SessionRegistryService
from app.services.sleep_coding import SleepCodingService
from app.services.task_registry import TaskRegistryService


@dataclass(frozen=True)
class ReviewSkillRunResult:
    output: ReviewSkillOutput
    token_usage: TokenUsage


class ReviewSkillService:
    def __init__(
        self,
        settings: Settings,
        agent_runtime: AgentRuntime | None = None,
        mcp_client: MCPClient | None = None,
    ) -> None:
        self.settings = settings
        self.skill_name = settings.resolved_review_skill_name
        self.command = settings.resolved_review_skill_command
        self.project_root = settings.project_root
        self.mcp_client = mcp_client or build_default_mcp_client(settings)
        self.agent_runtime = agent_runtime or AgentRuntime(
            settings,
            mcp_client=self.mcp_client,
        )
        self.token_counter = TokenCountingService()
        self.pricing = PricingRegistry(settings)

    def run(self, source: ReviewSource, context: str) -> ReviewSkillRunResult:
        command = self._resolve_command(source)
        if command is not None:
            return self._run_with_command(command, source, context)
        if self.settings.openai_api_key or self.settings.minimax_api_key:
            try:
                return self._run_with_agent_runtime(source, context)
            except Exception:
                if self.settings.app_env != "test":
                    raise
                return self._build_dry_run_output(source, context)
        return self._build_dry_run_output(source, context)

    def _run_with_agent_runtime(self, source: ReviewSource, context: str) -> ReviewSkillRunResult:
        response = self.agent_runtime.generate_structured_output(
            self._build_agent_descriptor(),
            user_prompt=(
                "Review the following code change context and return structured findings.\n\n"
                f"Source type: {source.source_type}\n\n"
                f"{context}"
            ),
            output_contract=(
                "Return strict JSON with keys `summary`, `findings`, `repair_strategy`, `blocking`, and `review_markdown`. "
                "`findings` must be an array of objects with keys `severity`, `title`, `detail`, and optional "
                "`file_path`, `line`, `suggestion`. Severity must be one of `P0`, `P1`, `P2`, `P3`. "
                "`blocking` must be true when any finding is P0 or P1, else false. "
                "`review_markdown` must be human-readable markdown that summarizes the findings."
            ),
        )
        output = ReviewSkillOutput.model_validate_json(response.output_text)
        return ReviewSkillRunResult(
            output=output.model_copy(
                update={
                    "run_mode": "real_run",
                    "review_markdown": output.review_markdown or self._render_review_markdown(output),
                }
            ),
            token_usage=response.usage.model_copy(update={"step_name": "code_review"}),
        )

    def _run_with_command(
        self,
        command: list[str],
        source: ReviewSource,
        context: str,
    ) -> ReviewSkillRunResult:
        prompt = self._build_prompt(source)
        review_dir = self._resolve_dir(source)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(context)
            context_path = Path(handle.name)

        try:
            completed = subprocess.run(
                [*command, prompt, "-f", str(context_path)],
                cwd=review_dir,
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            context_path.unlink(missing_ok=True)
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if completed.returncode != 0:
            raise RuntimeError(
                f"Review skill command failed with exit_code={completed.returncode}: {output}"
            )
        structured = self._parse_command_output(output)
        return ReviewSkillRunResult(
            output=structured,
            token_usage=self._estimate_usage(
                input_text=f"{prompt}\n\n{context}",
                output_text=output,
            ),
        )

    def _parse_command_output(self, output: str) -> ReviewSkillOutput:
        parsed_json = self._extract_json_object(output)
        if parsed_json is not None:
            structured = ReviewSkillOutput.model_validate(parsed_json)
            return structured.model_copy(
                update={
                    "run_mode": "real_run",
                    "review_markdown": structured.review_markdown or self._render_review_markdown(structured),
                }
            )
        findings = self._extract_findings_fallback(output)
        severity_counts = _count_findings_by_severity(findings)
        blocking = any(severity_counts.get(level, 0) > 0 for level in ("P0", "P1"))
        structured = ReviewSkillOutput(
            summary=self._extract_summary(output),
            findings=findings,
            repair_strategy=self._extract_repair_strategy(output),
            blocking=blocking,
            run_mode="real_run",
            review_markdown=output,
        )
        return structured

    def _build_dry_run_output(self, source: ReviewSource, context: str) -> ReviewSkillRunResult:
        summary = f"Dry-run review generated for {source.source_type}."
        review_markdown = (
            "## Code Review Agent\n\n"
            f"- Skill: `{self.skill_name}`\n"
            f"- Source Type: `{source.source_type}`\n"
            f"- Run Mode: `dry_run`\n\n"
            "### Summary\n"
            "Dry-run review executed because no review skill runtime is configured.\n\n"
            "### Context\n"
            f"{context}\n"
        )
        output = ReviewSkillOutput(
            summary=summary,
            findings=[],
            repair_strategy=["Configure a review skill runtime for structured findings."],
            blocking=False,
            run_mode="dry_run",
            review_markdown=review_markdown,
        )
        return ReviewSkillRunResult(
            output=output,
            token_usage=self._estimate_usage(
                input_text=context,
                output_text=review_markdown,
            ),
        )

    def _build_agent_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            agent_id="code-review-agent",
            workspace=self.settings.resolved_review_workspace,
            skill_names=self.settings.resolved_review_skills,
            mcp_servers=self.settings.resolved_review_mcp_servers,
            model_profile=self.settings.resolved_review_model_profile,
            system_instruction=(
                "Review code changes and return structured findings that automation can route."
            ),
        )

    def _resolve_command(self, source: ReviewSource) -> list[str] | None:
        if self.command:
            return shlex.split(self.command)
        if self.settings.app_env == "test":
            return None
        if which("opencode") is None:
            return None
        review_dir = self._resolve_dir(source)
        return [
            "opencode",
            "run",
            "--dir",
            str(review_dir),
            "--format",
            "default",
        ]

    def _resolve_dir(self, source: ReviewSource) -> Path:
        if source.local_path:
            return Path(source.local_path).expanduser()
        return self.project_root

    def _build_prompt(self, source: ReviewSource) -> str:
        return (
            f"Use the {self.skill_name} skill to review this source. "
            f"Source type: {source.source_type}. "
            "Return strict JSON with summary, findings, repair_strategy, blocking, and review_markdown."
        )

    def _extract_summary(self, output: str) -> str:
        if not output:
            return f"Review completed via {self.skill_name}."
        summary_match = re.search(
            r"^### Summary\s*\n(?P<summary>(?:- .*\n?|.*\n?)+?)(?:\n### |\Z)",
            output,
            flags=re.MULTILINE,
        )
        if summary_match:
            summary = " ".join(
                line.strip().lstrip("-").strip()
                for line in summary_match.group("summary").splitlines()
                if line.strip()
            )
            if summary:
                return summary
        change_summary_match = re.search(
            r"^### 变更摘要\s*\n(?P<summary>.+?)(?:\n---|\n### |\Z)",
            output,
            flags=re.MULTILINE | re.DOTALL,
        )
        if change_summary_match:
            summary = " ".join(
                line.strip()
                for line in change_summary_match.group("summary").splitlines()
                if line.strip()
            )
            if summary:
                return summary
        return output.splitlines()[0]

    def _extract_json_object(self, output: str) -> dict[str, object] | None:
        stripped = output.strip()
        candidates = [stripped]
        fenced = re.findall(r"```json\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
        candidates.extend(fenced)
        for candidate in candidates:
            if not candidate.startswith("{"):
                continue
            try:
                loaded = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                return loaded
        return None

    def _extract_findings_fallback(self, output: str) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        for line in output.splitlines():
            match = re.search(r"(?<![A-Z0-9])(P[0-3])(?![A-Z0-9])[:\s-]+(.+)", line)
            if not match:
                continue
            findings.append(
                ReviewFinding(
                    severity=match.group(1),  # type: ignore[arg-type]
                    title=match.group(2).strip()[:120],
                    detail=line.strip(),
                )
            )
        return findings

    def _extract_repair_strategy(self, output: str) -> list[str]:
        section = re.search(
            r"^### (Repair Strategy|修复建议)\s*\n(?P<body>(?:- .*\n?|.*\n?)+?)(?:\n### |\Z)",
            output,
            flags=re.MULTILINE,
        )
        if not section:
            return []
        strategies = [
            line.strip().lstrip("-").strip()
            for line in section.group("body").splitlines()
            if line.strip()
        ]
        return [item for item in strategies if item]

    def _render_review_markdown(self, output: ReviewSkillOutput) -> str:
        findings = (
            "\n".join(
                (
                    f"- [{finding.severity}] {finding.title}"
                    + (
                        f" ({finding.file_path}:{finding.line})"
                        if finding.file_path and finding.line
                        else f" ({finding.file_path})"
                        if finding.file_path
                        else ""
                    )
                    + f": {finding.detail}"
                )
                for finding in output.findings
            )
            if output.findings
            else "- No material findings."
        )
        repair = (
            "\n".join(f"- {item}" for item in output.repair_strategy)
            if output.repair_strategy
            else "- No repair actions required."
        )
        return (
            "## Code Review Agent\n\n"
            f"### Summary\n{output.summary}\n\n"
            "### Findings\n"
            f"{findings}\n\n"
            "### Repair Strategy\n"
            f"{repair}\n"
        )

    def _estimate_usage(
        self,
        *,
        input_text: str,
        output_text: str,
    ) -> TokenUsage:
        provider = self.settings.resolved_llm_default_provider
        model = self.settings.resolved_llm_default_model
        usage = self.token_counter.estimate_text_usage(
            provider=provider,
            model=model,
            input_text=input_text,
            output_text=output_text,
            existing_usage=TokenUsage(),
        )
        return usage.model_copy(
            update={
                "provider": provider,
                "model_name": model,
                "message_count": 2,
                "step_name": "code_review",
                "cost_usd": self.pricing.calculate_cost_usd(
                    provider=provider,
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                ),
            }
        )


class ReviewService:
    def __init__(
        self,
        settings: Settings | None = None,
        github: object | None = None,
        gitlab: GitLabService | None = None,
        sleep_coding: SleepCodingService | None = None,
        skill: ReviewSkillService | None = None,
        mcp_client: MCPClient | None = None,
        tasks: TaskRegistryService | None = None,
        sessions: SessionRegistryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.gitlab = gitlab or GitLabService(self.settings)
        self.sleep_coding = sleep_coding or SleepCodingService(settings=self.settings)
        self.skill = skill or ReviewSkillService(self.settings)
        self.tasks = tasks or TaskRegistryService(self.settings)
        self.sessions = sessions or SessionRegistryService(self.settings)
        self.mcp_client = mcp_client or build_default_mcp_client(self.settings)
        self.ledger = self.sleep_coding.ledger
        self.github_server = self.settings.mcp_github_server_name
        self.database_path = self.settings.resolved_database_path
        self.review_runs_dir = self.settings.resolved_review_runs_dir
        self._ensure_parent_dir()
        self._initialize_schema()

    def start_review(self, payload: ReviewRunRequest) -> ReviewRun:
        review_id = str(uuid4())
        source = self._normalize_source(payload.source)
        context = self._build_context(source)
        run_result = self.skill.run(source, context)
        structured = self._apply_blocking_override(source, run_result.output)
        review_usage = run_result.token_usage.model_copy(update={"step_name": "code_review"})
        severity_counts = _count_findings_by_severity(structured.findings)
        is_blocking = (
            structured.blocking
            if structured.blocking is not None
            else any(severity_counts.get(level, 0) > 0 for level in ("P0", "P1"))
        )
        content = structured.review_markdown or self.skill._render_review_markdown(structured)
        artifact_path = self._write_artifact(review_id, source, content)
        comment = self._write_comment(source, content)
        parent_control_task = self._resolve_parent_control_task(source)
        parent_run_session_id = (
            parent_control_task.payload.get("run_session_id")
            if parent_control_task
            else None
        )
        run_session = self.sessions.create_child_session(
            session_type="run_session",
            parent_session_id=parent_run_session_id,
            agent_id="code-review-agent",
            user_id=parent_control_task.user_id if parent_control_task else None,
            source=parent_control_task.source if parent_control_task else None,
            external_ref=f"review-run:{review_id}",
            payload={"source_type": source.source_type, "blocking": is_blocking},
        )
        control_task = self.tasks.create_task(
            task_type="code_review",
            agent_id="code-review-agent",
            status="completed",
            parent_task_id=parent_control_task.task_id if parent_control_task else None,
            repo=source.repo,
            issue_number=None,
            title=structured.summary,
            external_ref=f"review_run:{review_id}",
            payload={
                "review_id": review_id,
                "source_type": source.source_type,
                "blocking": is_blocking,
                "artifact_path": str(artifact_path),
                "comment_url": comment.html_url,
                "run_session_id": run_session.session_id,
            },
        )

        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO review_runs (
                    review_id,
                    control_task_id,
                    parent_task_id,
                    source_payload,
                    status,
                    artifact_path,
                    comment_url,
                    summary,
                    content,
                    findings_payload,
                    severity_counts_payload,
                    is_blocking,
                    run_mode,
                    task_id,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cache_read_tokens,
                    cache_write_tokens,
                    reasoning_tokens,
                    message_count,
                    duration_seconds,
                    model_name,
                    provider,
                    cost_usd,
                    step_name,
                    reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    review_id,
                    control_task.task_id,
                    control_task.parent_task_id,
                    source.model_dump_json(),
                    "completed",
                    str(artifact_path),
                    comment.html_url,
                    structured.summary,
                    content,
                    json.dumps([finding.model_dump(mode="json") for finding in structured.findings], ensure_ascii=True),
                    json.dumps(severity_counts, ensure_ascii=True),
                    1 if is_blocking else 0,
                    structured.run_mode,
                    source.task_id,
                    review_usage.prompt_tokens,
                    review_usage.completion_tokens,
                    review_usage.total_tokens,
                    review_usage.cache_read_tokens,
                    review_usage.cache_write_tokens,
                    review_usage.reasoning_tokens,
                    review_usage.message_count,
                    review_usage.duration_seconds,
                    review_usage.model_name,
                    review_usage.provider,
                    review_usage.cost_usd,
                    review_usage.step_name,
                ),
            )
            connection.commit()
        self._record_review_usage(source, review_usage)
        self.tasks.append_event(
            control_task.task_id,
            "review_completed",
            {
                "review_id": review_id,
                "blocking": is_blocking,
                "severity_counts": severity_counts,
                "token_usage": review_usage.model_dump(mode="json"),
            },
        )

        return self.get_review(review_id)

    def get_review(self, review_id: str) -> ReviewRun:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM review_runs WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Review not found: {review_id}")
        return self._deserialize_review(row)

    def _apply_blocking_override(
        self,
        source: ReviewSource,
        structured: ReviewSkillOutput,
    ) -> ReviewSkillOutput:
        if (
            not self.settings.resolved_review_force_blocking_first_pass
            or source.source_type != "sleep_coding_task"
            or not source.task_id
        ):
            return structured
        if self.count_blocking_reviews(source.task_id) > 0:
            return structured
        if structured.blocking:
            return structured
        synthetic_finding = ReviewFinding(
            severity="P1",
            title="Integration blocking checkpoint",
            detail=(
                "Forced blocking finding for integration validation. "
                "Ralph should apply one repair loop and re-run review."
            ),
            file_path=".sleep_coding/issue-checkpoint.md",
            line=1,
            suggestion="Update the generated task artifact to acknowledge the blocking review.",
        )
        findings = [synthetic_finding, *structured.findings]
        markdown = structured.review_markdown or self.skill._render_review_markdown(structured)
        markdown += (
            "\n\n### Integration Override\n"
            "- Forced a single blocking review pass to validate Ralph repair automation.\n"
        )
        return structured.model_copy(
            update={
                "summary": "Forced blocking review for integration validation.",
                "findings": findings,
                "repair_strategy": [
                    "Apply one follow-up change and rerun the review loop.",
                    *structured.repair_strategy,
                ],
                "blocking": True,
                "review_markdown": markdown,
            }
        )

    def apply_action(self, review_id: str, payload: ReviewActionRequest) -> ReviewRun:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM review_runs WHERE review_id = ?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Review not found: {review_id}")

            status_map = {
                "approve_review": "approved",
                "request_changes": "changes_requested",
                "cancel_review": "cancelled",
            }
            new_status = status_map[payload.action]
            connection.execute(
                """
                UPDATE review_runs
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE review_id = ?
                """,
                (new_status, review_id),
            )
            connection.commit()

        review = self.get_review(review_id)
        if review.control_task_id:
            self.tasks.update_task(review.control_task_id, status=new_status)
            self.tasks.append_event(
                review.control_task_id,
                f"review_{new_status}",
                {"review_id": review_id, "task_id": review.task_id},
            )
        if review.task_id:
            if review.source.repo and review.source.pr_number:
                if payload.action == "request_changes":
                    self._write_pr_review(
                        review.source,
                        event="REQUEST_CHANGES",
                        body=self._render_review_decision_comment(review, payload.action),
                    )
                elif payload.action == "approve_review":
                    self._write_pr_review(
                        review.source,
                        event="APPROVE",
                        body=self._render_review_decision_comment(review, payload.action),
                    )
            if payload.action == "request_changes":
                self.sleep_coding.apply_action(
                    review.task_id,
                    SleepCodingTaskActionRequest(action="request_changes"),
                )
            elif payload.action == "approve_review":
                task = self.sleep_coding.get_task(review.task_id)
                if task.status != "approved":
                    self.sleep_coding.apply_action(
                        review.task_id,
                        SleepCodingTaskActionRequest(action="approve_pr"),
                    )
        return self.get_review(review_id)

    def trigger_for_task(self, task_id: str) -> ReviewRun:
        task = self.sleep_coding.get_task(task_id)
        source = ReviewSource(
            source_type="sleep_coding_task",
            repo=task.repo,
            pr_number=task.pull_request.pr_number if task.pull_request else None,
            url=task.pull_request.html_url if task.pull_request else None,
            base_branch=task.base_branch,
            head_branch=task.head_branch,
            task_id=task.task_id,
        )
        return self.start_review(ReviewRunRequest(source=source))

    def list_task_reviews(self, task_id: str) -> list[ReviewRun]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM review_runs
                WHERE task_id = ?
                ORDER BY created_at ASC, review_id ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._deserialize_review(row) for row in rows]

    def count_blocking_reviews(self, task_id: str) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM review_runs
                WHERE task_id = ? AND is_blocking = 1
                """,
                (task_id,),
            ).fetchone()
        return int(row["count"]) if row else 0

    def _ensure_parent_dir(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self.review_runs_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            fallback_dir = Path(tempfile.gettempdir()) / "youmeng-gateway"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.database_path = fallback_dir / self.database_path.name
            self.review_runs_dir = fallback_dir / "review-runs"
            self.review_runs_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_runs (
                    review_id TEXT PRIMARY KEY,
                    control_task_id TEXT,
                    parent_task_id TEXT,
                    source_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    artifact_path TEXT,
                    comment_url TEXT,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    findings_payload TEXT NOT NULL DEFAULT '[]',
                    severity_counts_payload TEXT NOT NULL DEFAULT '{}',
                    is_blocking INTEGER NOT NULL DEFAULT 0,
                    run_mode TEXT NOT NULL,
                    task_id TEXT,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL NOT NULL DEFAULT 0,
                    model_name TEXT,
                    provider TEXT,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    step_name TEXT,
                    reviewed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(review_runs)")
            }
            if "findings_payload" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN findings_payload TEXT NOT NULL DEFAULT '[]'
                    """
                )
            if "control_task_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN control_task_id TEXT
                    """
                )
            if "parent_task_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN parent_task_id TEXT
                    """
                )
            if "severity_counts_payload" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN severity_counts_payload TEXT NOT NULL DEFAULT '{}'
                    """
                )
            if "is_blocking" not in columns:
                connection.execute(
                    """
                    ALTER TABLE review_runs
                    ADD COLUMN is_blocking INTEGER NOT NULL DEFAULT 0
                    """
                )
            for column_name, definition in {
                "prompt_tokens": "INTEGER NOT NULL DEFAULT 0",
                "completion_tokens": "INTEGER NOT NULL DEFAULT 0",
                "total_tokens": "INTEGER NOT NULL DEFAULT 0",
                "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
                "cache_write_tokens": "INTEGER NOT NULL DEFAULT 0",
                "reasoning_tokens": "INTEGER NOT NULL DEFAULT 0",
                "message_count": "INTEGER NOT NULL DEFAULT 0",
                "duration_seconds": "REAL NOT NULL DEFAULT 0",
                "model_name": "TEXT",
                "provider": "TEXT",
                "cost_usd": "REAL NOT NULL DEFAULT 0",
                "step_name": "TEXT",
            }.items():
                if column_name in columns:
                    continue
                connection.execute(
                    f"ALTER TABLE review_runs ADD COLUMN {column_name} {definition}"
                )
            connection.commit()

    def _normalize_source(self, source: ReviewSource) -> ReviewSource:
        if source.source_type == "sleep_coding_task":
            return source
        if source.url:
            github_match = re.match(
                r"https://github.com/(?P<repo>[^/]+/[^/]+)/pull/(?P<number>\d+)",
                source.url,
            )
            if github_match:
                return source.model_copy(
                    update={
                        "source_type": "github_pr",
                        "repo": github_match.group("repo"),
                        "pr_number": int(github_match.group("number")),
                    }
                )
            gitlab_match = re.match(
                r"https://gitlab.com/(?P<project>.+)/-/merge_requests/(?P<number>\d+)",
                source.url,
            )
            if gitlab_match:
                return source.model_copy(
                    update={
                        "source_type": "gitlab_mr",
                        "project_path": gitlab_match.group("project"),
                        "mr_number": int(gitlab_match.group("number")),
                    }
                )
        return source

    def _build_context(self, source: ReviewSource) -> str:
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
            return (
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
        if source.source_type == "local_code":
            return self._build_local_code_context(source)
        return (
            f"Source URL: {source.url or 'n/a'}\n"
            f"Repo: {source.repo or 'n/a'}\n"
            f"PR Number: {source.pr_number or 'n/a'}\n"
            f"MR Number: {source.mr_number or 'n/a'}\n"
            f"Project Path: {source.project_path or 'n/a'}\n"
        )

    def _build_local_code_context(self, source: ReviewSource) -> str:
        local_path = Path(source.local_path or self.settings.project_root).expanduser()
        base_branch = source.base_branch or "main"
        head_branch = source.head_branch
        if not (local_path / ".git").exists():
            return (
                f"Local Path: {local_path}\n"
                "Git metadata unavailable. Review the working tree content directly.\n"
            )

        diff_args = ["git", "diff", "--stat"]
        diff_target = "working-tree"
        if head_branch:
            merge_base = subprocess.run(
                ["git", "merge-base", base_branch, head_branch],
                cwd=local_path,
                capture_output=True,
                text=True,
                check=False,
            )
            base_ref = merge_base.stdout.strip() if merge_base.returncode == 0 else base_branch
            diff_args = ["git", "diff", "--stat", f"{base_ref}..{head_branch}"]
            diff_target = f"{base_ref}..{head_branch}"
            merge_base_note = (
                ""
                if merge_base.returncode == 0
                else f"Merge-base resolution failed; fallback to `{base_branch}`.\n"
            )
        else:
            base_ref = base_branch
            merge_base_note = ""

        diff = subprocess.run(
            diff_args,
            cwd=local_path,
            capture_output=True,
            text=True,
            check=False,
        )
        diff_body = self._format_git_output(
            completed=diff,
            success_label="Diff stat collected successfully.",
            failure_label=(
                "Diff stat unavailable. Review should fall back to the working tree "
                "and repository files."
            ),
        )
        detailed_diff = subprocess.run(
            ["git", "diff", "--unified=1"]
            if not head_branch
            else ["git", "diff", "--unified=1", f"{base_ref}..{head_branch}"],
            cwd=local_path,
            capture_output=True,
            text=True,
            check=False,
        )
        detailed_diff_body = self._format_git_output(
            completed=detailed_diff,
            success_label="Detailed diff collected successfully.",
            failure_label=(
                "Detailed diff unavailable. Review should rely on repository files "
                "and changed file summaries."
            ),
        )
        return (
            f"Local Path: {local_path}\n"
            f"Base Branch: {base_branch}\n"
            f"Head Branch: {head_branch or 'working-tree'}\n"
            f"Diff Target: {diff_target}\n"
            f"{merge_base_note}\n"
            "## Diff Stat\n"
            f"{diff_body}\n\n"
            "## Diff\n"
            f"{detailed_diff_body}\n"
        )

    def _format_git_output(
        self,
        completed: subprocess.CompletedProcess[str],
        success_label: str,
        failure_label: str,
    ) -> str:
        output = completed.stdout.strip() or completed.stderr.strip()
        if completed.returncode == 0:
            return output or success_label
        return (
            f"{failure_label}\n"
            f"Exit code: {completed.returncode}\n"
            f"Git output: {output or 'n/a'}"
        )

    def _write_artifact(self, review_id: str, source: ReviewSource, content: str) -> Path:
        filename = self._artifact_name(review_id, source)
        artifact_path = self.review_runs_dir / filename
        artifact_path.write_text(content, encoding="utf-8")
        return artifact_path

    def _artifact_name(self, review_id: str, source: ReviewSource) -> str:
        if source.source_type == "github_pr" and source.pr_number:
            return f"github-pr-{source.pr_number}-review.md"
        if source.source_type == "gitlab_mr" and source.mr_number:
            return f"gitlab-mr-{source.mr_number}-review.md"
        if source.source_type == "sleep_coding_task" and source.task_id:
            return f"task-{source.task_id}-review.md"
        return f"local-review-{review_id}.md"

    def _write_comment(self, source: ReviewSource, content: str) -> GitHubCommentResult:
        if source.source_type == "github_pr" and source.repo and source.pr_number:
            return self._write_pr_review(source, event="COMMENT", body=content)
        if source.source_type == "sleep_coding_task" and source.repo and source.pr_number:
            return self._write_pr_review(source, event="COMMENT", body=content)
        if source.source_type == "gitlab_mr" and source.project_path and source.mr_number:
            return self.gitlab.create_merge_request_comment(
                project_path=source.project_path,
                mr_number=source.mr_number,
                body=content,
            )
        return GitHubCommentResult(html_url=source.url, is_dry_run=True)

    def _write_pr_review(
        self,
        source: ReviewSource,
        *,
        event: str,
        body: str,
    ) -> GitHubCommentResult:
        server = self._require_github_server("pull_request_review_write")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="pull_request_review_write",
                arguments={
                    "repo": source.repo,
                    "pr_number": source.pr_number,
                    "method": "create",
                    "event": event,
                    "body": body,
                },
            )
        )
        payload = self._coerce_mapping(result.content)
        return GitHubCommentResult(
            html_url=self._coerce_html_url(payload) or source.url,
            is_dry_run=False,
        )

    def _render_review_decision_comment(
        self,
        review: ReviewRun,
        action: str,
    ) -> str:
        decision_label = {
            "approve_review": "Approved",
            "request_changes": "Changes Requested",
            "cancel_review": "Cancelled",
        }.get(action, review.status)
        severity_parts = [
            f"{level}={review.severity_counts.get(level, 0)}"
            for level in ("P0", "P1", "P2", "P3")
            if review.severity_counts.get(level, 0) > 0
        ]
        findings = review.findings[:5]
        finding_lines = (
            [
                f"- [{item.severity}] {item.title}: {item.detail}"
                for item in findings
            ]
            if findings
            else ["- No material findings."]
        )
        return "\n".join(
            [
                "## Ralph Review Decision",
                f"- Decision: {decision_label}",
                f"- Blocking: {'yes' if review.is_blocking else 'no'}",
                f"- Summary: {review.summary or 'n/a'}",
                f"- Severity: {', '.join(severity_parts) if severity_parts else 'No material findings'}",
                f"- Artifact: {review.artifact_path or 'n/a'}",
                f"- Review Link: {review.comment_url or 'n/a'}",
                "",
                "### Findings",
                *finding_lines,
                "",
                "### Token Usage",
                f"- Input Token: {review.token_usage.prompt_tokens:,}",
                f"- Output Token: {review.token_usage.completion_tokens:,}",
                f"- Total Token: {review.token_usage.total_tokens:,}",
                f"- Cache Read Token: {review.token_usage.cache_read_tokens:,}",
                f"- Cache Write Token: {review.token_usage.cache_write_tokens:,}",
                f"- Reasoning Token: {review.token_usage.reasoning_tokens:,}",
                f"- Messages: {review.token_usage.message_count:,}",
                f"- Duration: {review.token_usage.duration_seconds:.2f} seconds",
                f"- Cost: ${review.token_usage.cost_usd:.3f}",
            ]
        )

    def _coerce_mapping(self, content: object) -> dict[str, object]:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    return item
        return {}

    def _require_github_server(self, tool: str) -> str:
        if self.github_server not in self.mcp_client.available_servers():
            raise RuntimeError(
                f"GitHub MCP server `{self.github_server}` is not configured. Define it in {self.settings.resolved_mcp_config_path.name}."
            )
        if not self.mcp_client.has_tool(self.github_server, tool):
            raise RuntimeError(
                f"GitHub MCP server `{self.github_server}` does not expose required tool `{tool}`."
            )
        return self.github_server

    def _coerce_html_url(self, payload: dict[str, object]) -> str | None:
        for key in ("html_url", "url"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _deserialize_review(self, row: sqlite3.Row) -> ReviewRun:
        findings = [
            ReviewFinding.model_validate(item)
            for item in json.loads(row["findings_payload"] or "[]")
        ]
        return ReviewRun(
            review_id=row["review_id"],
            control_task_id=row["control_task_id"],
            parent_task_id=row["parent_task_id"],
            source=ReviewSource.model_validate_json(row["source_payload"]),
            status=row["status"],
            artifact_path=row["artifact_path"],
            comment_url=row["comment_url"],
            summary=row["summary"],
            content=row["content"],
            findings=findings,
            severity_counts=json.loads(row["severity_counts_payload"] or "{}"),
            is_blocking=bool(row["is_blocking"]),
            run_mode=row["run_mode"],
            task_id=row["task_id"],
            token_usage=TokenUsage(
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                total_tokens=row["total_tokens"],
                cache_read_tokens=row["cache_read_tokens"],
                cache_write_tokens=row["cache_write_tokens"],
                reasoning_tokens=row["reasoning_tokens"],
                message_count=row["message_count"],
                duration_seconds=float(row["duration_seconds"] or 0.0),
                model_name=row["model_name"],
                provider=row["provider"],
                cost_usd=float(row["cost_usd"] or 0.0),
                step_name=row["step_name"],
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            reviewed_at=row["reviewed_at"],
        )

    def _resolve_parent_control_task(self, source: ReviewSource):
        if source.task_id:
            sleep_task = self.sleep_coding.get_task(source.task_id)
            if sleep_task.control_task_id:
                return self.tasks.get_task(sleep_task.control_task_id)
        if source.repo and source.pr_number:
            return self.tasks.find_task_by_external_ref(
                f"github_pr:{source.repo}#{source.pr_number}",
            )
        return None

    def _record_review_usage(self, source: ReviewSource, usage: TokenUsage) -> None:
        if not source.task_id:
            return
        sleep_task = self.sleep_coding.get_task(source.task_id)
        if not sleep_task.kickoff_request_id:
            return
        try:
            self.ledger.append_usage(
                request_id=sleep_task.kickoff_request_id,
                run_id=str(uuid4()),
                usage=usage,
                step_name=usage.step_name,
            )
        except ValueError:
            return


def _count_findings_by_severity(findings: list[ReviewFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts
