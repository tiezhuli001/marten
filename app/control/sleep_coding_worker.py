from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

from app.agents.ralph import SleepCodingService
from app.control.events import ControlEventType
from app.control.task_registry import TaskRegistryService
from app.core.config import Settings, get_settings
from app.control.sleep_coding_worker_store import SleepCodingWorkerStore
from app.models.schemas import (
    SleepCodingTask,
    SleepCodingTaskActionRequest,
    SleepCodingTaskRequest,
    SleepCodingWorkerClaim,
    SleepCodingWorkerPollRequest,
    SleepCodingWorkerPollResponse,
    WorkerDiscoveredIssue,
)
from app.runtime.mcp import MCPClient, MCPToolCall, build_default_mcp_client


class SleepCodingWorkerService:
    _ACTIVE_TASK_STATUSES = {
        "created",
        "planning",
        "awaiting_confirmation",
        "coding",
        "validating",
        "pr_opened",
        "in_review",
        "changes_requested",
    }

    def __init__(
        self,
        settings: Settings | None = None,
        mcp_client: MCPClient | None = None,
        sleep_coding: SleepCodingService | None = None,
        tasks: TaskRegistryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.mcp_client = mcp_client or build_default_mcp_client(self.settings)
        self.sleep_coding = sleep_coding or SleepCodingService(self.settings)
        self.tasks = tasks or TaskRegistryService(self.settings)
        self.store = SleepCodingWorkerStore(self.settings.resolved_database_path)
        self.database_path = self.store.database_path
        self.poll_labels = self.settings.resolved_sleep_coding_worker_poll_labels
        self.lease_seconds = max(self.settings.resolved_sleep_coding_worker_lease_seconds, 1)
        self.heartbeat_timeout_seconds = max(self.settings.resolved_sleep_coding_worker_heartbeat_timeout_seconds, 1)
        self.max_retries = max(self.settings.resolved_sleep_coding_worker_max_retries, 0)
        self.retry_backoff_seconds = max(self.settings.resolved_sleep_coding_worker_retry_backoff_seconds, 1)

    def poll_once(
        self,
        payload: SleepCodingWorkerPollRequest | None = None,
    ) -> SleepCodingWorkerPollResponse:
        request = payload or SleepCodingWorkerPollRequest()
        repo = request.repo or self.settings.resolved_github_repository
        if not repo:
            raise ValueError("GitHub repository is not configured")
        auto_approve_plan = (
            request.auto_approve_plan
            if request.auto_approve_plan is not None
            else self.settings.resolved_sleep_coding_worker_auto_approve_plan
        )
        discovered = self._list_open_issues(repo=repo, limit=request.limit)
        tasks: list[SleepCodingTask] = []
        with closing(self._connect()) as connection:
            timed_out_updates = self._expire_stale_claims(connection, repo)
            self._sync_claim_statuses(connection, repo)
            connection.commit()
        for control_task_id, domain_task_id in timed_out_updates:
            self.tasks.update_task(
                control_task_id,
                status="timed_out",
                payload_patch={"last_error": "Worker lease expired or heartbeat timed out."},
            )
            self.tasks.append_event(
                control_task_id,
                "worker_timed_out",
                {"domain_task_id": domain_task_id},
            )
        for issue in discovered:
            should_process = False
            with closing(self._connect()) as connection:
                self.store.record_discovered_issue(connection, repo, request.worker_id, issue)
                if not self._is_issue_eligible(issue):
                    self.store.mark_claim_status(connection, repo, issue.issue_number, "skipped")
                elif not self._is_ready_for_retry(connection, repo, issue.issue_number):
                    self.store.mark_claim_status(connection, repo, issue.issue_number, "retry_pending")
                elif self._has_active_task(connection, repo, issue.issue_number):
                    self._sync_claim_statuses(connection, repo)
                else:
                    self._acquire_lease(connection, repo, issue.issue_number, request.worker_id)
                    should_process = True
                connection.commit()
            if not should_process:
                continue
            task: SleepCodingTask | None = None
            try:
                task = self.sleep_coding.start_task(
                    SleepCodingTaskRequest(
                        issue_number=issue.issue_number,
                        repo=repo,
                        issue_title=issue.title,
                        issue_body=issue.body,
                        request_id=self._resolve_parent_request_id(repo, issue.issue_number),
                        notify_plan_ready=True,
                    )
                )
                if task.control_task_id:
                    self.tasks.append_domain_event(
                        task.control_task_id,
                        ControlEventType.TASK_CLAIMED,
                        {
                            "domain_task_id": task.task_id,
                            "issue_number": issue.issue_number,
                            "worker_id": request.worker_id,
                        },
                    )
                with closing(self._connect()) as update_connection:
                    self._heartbeat(update_connection, repo, issue.issue_number, request.worker_id)
                    self.store.attach_task_to_claim(
                        connection=update_connection,
                        repo=repo,
                        worker_id=request.worker_id,
                        issue=issue,
                        task=task,
                        status=task.status,
                    )
                    update_connection.commit()
                if auto_approve_plan:
                    task = self.sleep_coding.apply_action(
                        task.task_id,
                        SleepCodingTaskActionRequest(action="approve_plan"),
                    )
                with closing(self._connect()) as update_connection:
                    self._heartbeat(update_connection, repo, issue.issue_number, request.worker_id)
                    self.store.attach_task_to_claim(
                        connection=update_connection,
                        repo=repo,
                        worker_id=request.worker_id,
                        issue=issue,
                        task=task,
                        status=task.status,
                    )
                    self._release_lease(update_connection, repo, issue.issue_number, task.status)
                    update_connection.commit()
                tasks.append(task)
            except Exception as exc:
                with closing(self._connect()) as update_connection:
                    if task is None:
                        self._record_failure(
                            update_connection,
                            repo,
                            issue.issue_number,
                            request.worker_id,
                            str(exc),
                        )
                    else:
                        latest_task = self.sleep_coding.get_task(task.task_id)
                        self._heartbeat(update_connection, repo, issue.issue_number, request.worker_id)
                        self.store.attach_task_to_claim(
                            connection=update_connection,
                            repo=repo,
                            worker_id=request.worker_id,
                            issue=issue,
                            task=latest_task,
                            status=latest_task.status,
                        )
                        update_connection.execute(
                            """
                            UPDATE sleep_coding_issue_claims
                            SET last_error = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE repo = ? AND issue_number = ?
                            """,
                            (str(exc), repo, issue.issue_number),
                        )
                        self._release_lease(update_connection, repo, issue.issue_number, latest_task.status)
                    update_connection.commit()
        with closing(self._connect()) as connection:
            claims = self.store.list_claims(connection, repo)
        return SleepCodingWorkerPollResponse(
            repo=repo,
            worker_id=request.worker_id,
            auto_approve_plan=auto_approve_plan,
            discovered_count=len(discovered),
            claimed_count=len(tasks),
            skipped_count=max(len(discovered) - len(tasks), 0),
            tasks=tasks,
            claims=claims,
        )

    def list_claims(self, repo: str | None = None) -> list[SleepCodingWorkerClaim]:
        target_repo = repo or self.settings.resolved_github_repository
        if not target_repo:
            raise ValueError("GitHub repository is not configured")
        with closing(self._connect()) as connection:
            self._sync_claim_statuses(connection, target_repo)
            connection.commit()
            return self.store.list_claims(connection, target_repo)

    def _connect(self) -> sqlite3.Connection:
        return self.store.connect()

    def _resolve_parent_request_id(
        self,
        repo: str,
        issue_number: int,
    ) -> str | None:
        parent = self.tasks.find_parent_for_issue(repo, issue_number)
        if parent is None:
            return None
        request_id = parent.payload.get("request_id")
        return request_id if isinstance(request_id, str) and request_id.strip() else None

    def _has_active_task(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
    ) -> bool:
        del connection
        active_task = self.tasks.find_latest_issue_task(
            repo=repo,
            issue_number=issue_number,
            task_type="sleep_coding",
            statuses=self._ACTIVE_TASK_STATUSES,
        )
        return active_task is not None


    def _list_open_issues(
        self,
        *,
        repo: str,
        limit: int,
    ) -> list[WorkerDiscoveredIssue]:
        server = self._require_github_server("list_issues")
        result = self.mcp_client.call_tool(
            MCPToolCall(
                server=server,
                tool="list_issues",
                arguments={"repo": repo, "state": "open", "limit": limit},
            )
        )
        return self._coerce_discovered_issues(result.content)

    def _require_github_server(self, tool: str) -> str:
        server = self.settings.mcp_github_server_name
        if server not in self.mcp_client.available_servers():
            raise RuntimeError(
                f"GitHub MCP server `{server}` is not configured. Define it in {self.settings.resolved_mcp_config_path.name}."
            )
        if not self.mcp_client.has_tool(server, tool):
            raise RuntimeError(
                f"GitHub MCP server `{server}` does not expose required tool `{tool}`."
            )
        return server

    def _coerce_discovered_issues(self, content: object) -> list[WorkerDiscoveredIssue]:
        raw_items: list[object]
        if isinstance(content, dict):
            issues = content.get("issues")
            raw_items = issues if isinstance(issues, list) else []
        elif isinstance(content, list):
            raw_items = content
        else:
            raise ValueError("MCP issue listing did not return a supported payload")
        discovered: list[WorkerDiscoveredIssue] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            labels_raw = item.get("labels", [])
            labels: list[str] = []
            if isinstance(labels_raw, list):
                for label in labels_raw:
                    if isinstance(label, dict):
                        name = label.get("name")
                        if isinstance(name, str) and name.strip():
                            labels.append(name.strip())
                    elif isinstance(label, str) and label.strip():
                        labels.append(label.strip())
            number = item.get("number")
            if not isinstance(number, int):
                continue
            discovered.append(
                WorkerDiscoveredIssue(
                    issue_number=number,
                    title=str(item.get("title") or f"GitHub issue #{number}"),
                    body=str(item.get("body") or ""),
                    state=str(item.get("state") or "open").lower(),
                    html_url=(
                        str(item.get("html_url"))
                        if item.get("html_url")
                        else f"https://github.com/{self.settings.resolved_github_repository}/issues/{number}"
                    ),
                    labels=labels,
                    is_dry_run=False,
                )
            )
        return discovered

    def _sync_claim_statuses(
        self,
        connection: sqlite3.Connection,
        repo: str,
    ) -> None:
        try:
            rows = connection.execute(
                """
                SELECT claims.repo,
                       claims.issue_number,
                       claims.task_id,
                       claims.status AS claim_status,
                       latest.external_ref AS latest_external_ref,
                       latest.status AS task_status,
                       latest.payload AS task_payload
                FROM sleep_coding_issue_claims AS claims
                LEFT JOIN (
                    SELECT ranked.repo,
                           ranked.issue_number,
                           ranked.external_ref,
                           ranked.status,
                           ranked.payload
                    FROM (
                        SELECT repo,
                               issue_number,
                               external_ref,
                               status,
                               payload,
                               created_at,
                               ROW_NUMBER() OVER (
                                   PARTITION BY repo, issue_number
                                   ORDER BY datetime(created_at) DESC, rowid DESC
                               ) AS rank_index
                        FROM control_tasks
                        WHERE task_type = 'sleep_coding'
                    ) AS ranked
                    WHERE ranked.rank_index = 1
                ) AS latest
                  ON latest.repo = claims.repo AND latest.issue_number = claims.issue_number
                WHERE claims.repo = ?
                """,
                (repo,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return
            raise
        for row in rows:
            latest_task_id = self._extract_domain_task_id(row["latest_external_ref"])
            task_status = row["task_status"]
            if not latest_task_id or not task_status:
                continue
            if latest_task_id == row["task_id"] and task_status == row["claim_status"]:
                continue
            payload = self._decode_control_payload(row["task_payload"])
            lease_expires_at = None if task_status not in self._ACTIVE_TASK_STATUSES else connection.execute(
                """
                SELECT lease_expires_at
                FROM sleep_coding_issue_claims
                WHERE repo = ? AND issue_number = ?
                """,
                (row["repo"], row["issue_number"]),
            ).fetchone()["lease_expires_at"]
            connection.execute(
                """
                UPDATE sleep_coding_issue_claims
                SET task_id = ?,
                    status = ?,
                    lease_expires_at = ?,
                    last_error = COALESCE(?, last_error),
                    updated_at = CURRENT_TIMESTAMP
                WHERE repo = ? AND issue_number = ?
                """,
                (
                    latest_task_id,
                    task_status,
                    lease_expires_at,
                    payload.get("last_error"),
                    row["repo"],
                    row["issue_number"],
                ),
            )

    def _decode_control_payload(self, payload: str | None) -> dict[str, object]:
        if not payload:
            return {}
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def _extract_domain_task_id(self, external_ref: str | None) -> str | None:
        if not external_ref:
            return None
        prefix = "sleep_coding_task:"
        if not external_ref.startswith(prefix):
            return None
        task_id = external_ref.removeprefix(prefix).strip()
        return task_id or None

    def _is_issue_eligible(self, issue: WorkerDiscoveredIssue) -> bool:
        issue_labels = set(issue.labels)
        required_labels = set(self.poll_labels)
        return required_labels.issubset(issue_labels)

    def _acquire_lease(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        worker_id: str,
    ) -> None:
        now = self._utcnow()
        self.store.acquire_lease(
            connection,
            repo,
            issue_number,
            worker_id,
            lease_expires_at=self._format_dt(now + timedelta(seconds=self.lease_seconds)),
            heartbeat_at=self._format_dt(now),
        )

    def _heartbeat(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        worker_id: str,
    ) -> None:
        now = self._utcnow()
        self.store.heartbeat(
            connection,
            repo,
            issue_number,
            worker_id,
            lease_expires_at=self._format_dt(now + timedelta(seconds=self.lease_seconds)),
            heartbeat_at=self._format_dt(now),
        )

    def _release_lease(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        status: str,
    ) -> None:
        self.store.release_lease(connection, repo, issue_number, status)

    def _record_failure(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
        worker_id: str,
        error_text: str,
    ) -> None:
        row = self.store.get_retry_state(connection, repo, issue_number)
        retry_count = int(row["retry_count"]) + 1 if row else 1
        status = "retrying" if retry_count <= self.max_retries else "failed"
        self.store.record_failure(
            connection,
            repo,
            issue_number,
            worker_id,
            error_text,
            retry_count=retry_count,
            next_retry_at=self._format_dt(
                self._utcnow() + timedelta(seconds=self.retry_backoff_seconds)
            ),
            status=status,
        )

    def _is_ready_for_retry(
        self,
        connection: sqlite3.Connection,
        repo: str,
        issue_number: int,
    ) -> bool:
        row = self.store.get_retry_state(connection, repo, issue_number)
        if row is None:
            return True
        if row["status"] != "retrying":
            return True
        if not row["next_retry_at"]:
            return True
        return row["next_retry_at"] <= self._format_dt(self._utcnow())

    def _expire_stale_claims(
        self,
        connection: sqlite3.Connection,
        repo: str,
    ) -> list[tuple[str, str]]:
        rows = connection.execute(
            """
            SELECT repo, issue_number, task_id, lease_expires_at, last_heartbeat_at
            FROM sleep_coding_issue_claims
            WHERE repo = ? AND status = 'claimed'
            """,
            (repo,),
        ).fetchall()
        now = self._utcnow()
        timed_out_updates: list[tuple[str, str]] = []
        for row in rows:
            lease_expires_at = self._parse_dt(row["lease_expires_at"])
            heartbeat_at = self._parse_dt(row["last_heartbeat_at"])
            lease_expired = lease_expires_at is not None and lease_expires_at < now
            heartbeat_stale = heartbeat_at is not None and (now - heartbeat_at).total_seconds() > self.heartbeat_timeout_seconds
            if not lease_expired and not heartbeat_stale:
                continue
            self.store.expire_claim(connection, row["repo"], row["issue_number"])
            if row["task_id"]:
                try:
                    task = self.sleep_coding.get_task(row["task_id"])
                except Exception:
                    continue
                if task.control_task_id:
                    timed_out_updates.append((task.control_task_id, task.task_id))
        return timed_out_updates

    def _utcnow(self) -> datetime:
        return datetime.now(UTC)

    def _format_dt(self, value: datetime) -> str:
        return value.isoformat()

    def _parse_dt(self, value: str | None) -> datetime | None:
        return self.store.parse_dt(value)
