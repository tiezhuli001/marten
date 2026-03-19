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

from app.agents.code_review_agent.bridge import ReviewCommentBridge
from app.agents.code_review_agent.context import ReviewContextBuilder
from app.agents.code_review_agent.store import ReviewRunStore, ReviewSourceSupport
from app.control.context import ContextAssemblyService
from app.control.events import ControlEventType
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
from app.services.gitlab import GitLabService
from app.services.session_registry import SessionRegistryService
from app.agents.ralph import SleepCodingService
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
        return AgentDescriptor.from_spec(self.settings.resolve_agent_spec("code-review-agent"))

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
        self.context = ContextAssemblyService(self.sessions)
        self.source_support = ReviewSourceSupport(self.settings, self.context)
        self.mcp_client = mcp_client or build_default_mcp_client(self.settings)
        self.ledger = self.sleep_coding.ledger
        self.github_server = self.settings.mcp_github_server_name
        self.bridge = ReviewCommentBridge(
            github_server=self.github_server,
            mcp_client=self.mcp_client,
            gitlab=self.gitlab,
            mcp_config_name=self.settings.resolved_mcp_config_path.name,
        )
        self.store = ReviewRunStore(self.settings)
        self.context_builder = ReviewContextBuilder(
            context=self.context,
            sleep_coding=self.sleep_coding,
            source_support=self.source_support,
        )
        self.database_path = self.store.database_path
        self.review_runs_dir = self.store.review_runs_dir

    def _sync_helpers(self) -> None:
        self.bridge.mcp_client = self.mcp_client
        self.bridge.github_server = self.github_server

    def start_review(self, payload: ReviewRunRequest) -> ReviewRun:
        self._sync_helpers()
        review_id = str(uuid4())
        source = self._normalize_source(payload.source)
        parent_control_task = self._resolve_parent_control_task(source)
        parent_run_session_id = (
            parent_control_task.payload.get("run_session_id")
            if parent_control_task
            else None
        )
        context = self.context_builder.build_context(source, parent_run_session_id)
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
        comment = self.bridge.write_comment(source, content)
        run_session = self.sessions.create_child_session(
            session_type="run_session",
            parent_session_id=parent_run_session_id,
            agent_id="code-review-agent",
            user_id=parent_control_task.user_id if parent_control_task else None,
            source=parent_control_task.source if parent_control_task else None,
            external_ref=f"review-run:{review_id}",
            payload={"source_type": source.source_type, "blocking": is_blocking},
        )
        self.context.record_short_memory(
            run_session.session_id,
            f"Review completed for {source.source_type}; blocking={is_blocking}; summary={structured.summary}",
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
        self.tasks.append_domain_event(
            control_task.task_id,
            ControlEventType.REVIEW_COMPLETED,
            {
                "review_id": review_id,
                "blocking": is_blocking,
                "severity_counts": severity_counts,
                "token_usage": review_usage.model_dump(mode="json"),
            },
        )

        return self.get_review(review_id)

    def get_review(self, review_id: str) -> ReviewRun:
        return self.store.get_review(review_id)

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
        self._sync_helpers()
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
            self.tasks.append_domain_event(
                review.control_task_id,
                (
                    ControlEventType.REVIEW_APPROVED
                    if new_status == "approved"
                    else ControlEventType.REVIEW_CHANGES_REQUESTED
                    if new_status == "changes_requested"
                    else f"review.{new_status}"
                ),
                {"review_id": review_id, "task_id": review.task_id},
            )
        if review.task_id:
            if review.source.repo and review.source.pr_number:
                if payload.action == "request_changes":
                    self.bridge.write_pr_review(
                        review.source,
                        event="REQUEST_CHANGES",
                        body=self.bridge.render_review_decision_comment(review, payload.action),
                    )
                elif payload.action == "approve_review":
                    self.bridge.write_pr_review(
                        review.source,
                        event="APPROVE",
                        body=self.bridge.render_review_decision_comment(review, payload.action),
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
        return self.store.list_task_reviews(task_id)

    def count_blocking_reviews(self, task_id: str) -> int:
        return self.store.count_blocking_reviews(task_id)

    def _ensure_parent_dir(self) -> None:
        self.store.ensure_parent_dir()

    def _connect(self) -> sqlite3.Connection:
        return self.store.connect()

    def _initialize_schema(self) -> None:
        self.store.initialize_schema()

    def _normalize_source(self, source: ReviewSource) -> ReviewSource:
        return self.source_support.normalize_source(source)

    def _build_context(
        self,
        source: ReviewSource,
        run_session_id: str | None = None,
    ) -> str:
        return self.context_builder.build_context(source, run_session_id)

    def _build_local_code_context(self, source: ReviewSource) -> str:
        return self.source_support.build_local_code_context(source)

    def _format_git_output(
        self,
        completed: subprocess.CompletedProcess[str],
        success_label: str,
        failure_label: str,
    ) -> str:
        return self.source_support.format_git_output(completed, success_label, failure_label)

    def _write_artifact(self, review_id: str, source: ReviewSource, content: str) -> Path:
        return self.store.write_artifact(review_id, source, content)

    def _artifact_name(self, review_id: str, source: ReviewSource) -> str:
        return self.store.artifact_name(review_id, source)

    def _write_comment(self, source: ReviewSource, content: str) -> GitHubCommentResult:
        return self.bridge.write_comment(source, content)

    def _write_pr_review(
        self,
        source: ReviewSource,
        *,
        event: str,
        body: str,
    ) -> GitHubCommentResult:
        return self.bridge.write_pr_review(source, event=event, body=body)

    def _render_review_decision_comment(
        self,
        review: ReviewRun,
        action: str,
    ) -> str:
        return self.bridge.render_review_decision_comment(review, action)

    def _coerce_mapping(self, content: object) -> dict[str, object]:
        return self.bridge.coerce_mapping(content)

    def _require_github_server(self, tool: str) -> str:
        return self.bridge.require_github_server(tool)

    def _coerce_html_url(self, payload: dict[str, object]) -> str | None:
        return self.bridge.coerce_html_url(payload)

    def _deserialize_review(self, row: sqlite3.Row) -> ReviewRun:
        return self.store.deserialize_review(row)

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
