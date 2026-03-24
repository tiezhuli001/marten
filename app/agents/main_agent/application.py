from __future__ import annotations

import json
import re
from typing import Any
from time import sleep
from collections.abc import Callable
from uuid import uuid4

from pydantic import ValidationError

from app.control.context import ContextAssemblyService
from app.control.events import ControlEventType
from app.core.config import Settings
from app.channel.notifications import ChannelNotificationService
from app.ledger.service import TokenLedgerService
from app.models.schemas import (
    GitHubIssueDraft,
    GitHubIssueResult,
    MainAgentCodingHandoff,
    MainAgentIntakeRequest,
    MainAgentIntakeResponse,
    TokenUsage,
)
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.llm import SharedLLMRuntime
from app.runtime.mcp import MCPClient, MCPToolCall, build_default_mcp_client
from app.runtime.structured_output import parse_structured_object
from app.runtime.token_counting import TokenCountingService
from app.control.session_registry import (
    SessionRegistryService,
    build_agent_session_external_ref,
    build_user_session_external_ref,
)
from app.control.task_registry import TaskRegistryService


class MainAgentService:
    def __init__(
        self,
        settings: Settings,
        channel: ChannelNotificationService | None = None,
        llm_runtime: SharedLLMRuntime | None = None,
        agent_runtime: AgentRuntime | None = None,
        mcp_client: MCPClient | None = None,
        tasks: TaskRegistryService | None = None,
        sessions: SessionRegistryService | None = None,
        ledger: TokenLedgerService | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings
        self.channel = channel or ChannelNotificationService(settings)
        self.llm_runtime = llm_runtime or SharedLLMRuntime(settings)
        self.token_counter = TokenCountingService()
        self.mcp_client = mcp_client or build_default_mcp_client(settings)
        self.agent_runtime = agent_runtime or AgentRuntime(
            settings,
            llm_runtime=self.llm_runtime,
            mcp_client=self.mcp_client,
        )
        self.tasks = tasks or TaskRegistryService(settings)
        self.sessions = sessions or SessionRegistryService(settings)
        self.context = ContextAssemblyService(self.sessions)
        self.ledger = ledger or TokenLedgerService(settings)
        self.sleep_fn = sleep_fn or ((lambda seconds: None) if settings.app_env == "test" else sleep)

    def intake(self, payload: MainAgentIntakeRequest) -> MainAgentIntakeResponse:
        repo = payload.repo or self.settings.resolved_github_repository
        user_session_ref = build_user_session_external_ref(
            source=payload.source,
            user_id=payload.user_id,
            session_key=payload.session_key,
        )
        user_session = self.sessions.get_or_create_session(
            session_type="user_session",
            external_ref=user_session_ref,
            user_id=payload.user_id,
            source=payload.source,
        )
        self.sessions.set_active_agent(user_session.session_id, "main-agent")
        agent_session = self.sessions.get_or_create_session(
            session_type="agent_session",
            external_ref=build_agent_session_external_ref(
                agent_id="main-agent",
                user_session_ref=user_session_ref,
            ),
            agent_id="main-agent",
            user_id=payload.user_id,
            source=payload.source,
            parent_session_id=user_session.session_id,
            payload={"workspace": str(self.settings.resolved_main_agent_workspace)},
        )
        mode, usage, chat_response, handoff = self._build_main_agent_output(
            payload,
            user_session.session_id,
            repo=repo,
        )
        request_id = payload.request_id or str(uuid4())
        run_id = payload.run_id or str(uuid4())
        usage_step = "main_agent_chat" if mode == "chat" else "main_agent_issue_intake"
        usage = usage.model_copy(update={"step_name": usage_step})
        if payload.persist_usage:
            usage = self.ledger.record_request(
                request_id=request_id,
                run_id=run_id,
                user_id=payload.user_id,
                source=payload.source,
                intent="general" if mode == "chat" else "sleep_coding",
                content=payload.content,
                usage=usage,
                step_name=usage_step,
            )
        if mode == "chat":
            response_message = chat_response or "Main Agent kept the request in chat mode."
            self.context.record_short_memory(
                user_session.session_id,
                f"Main Agent answered in chat mode: {response_message}",
            )
            self.context.record_short_memory(
                agent_session.session_id,
                "Main Agent kept the request in chat mode and did not create a coding handoff.",
            )
            return MainAgentIntakeResponse(
                mode="chat",
                issue=None,
                message=response_message,
                chat_response=response_message,
                handoff=None,
                token_usage=usage,
                control_task_id=None,
            )
        if not repo:
            raise ValueError("GitHub repository is not configured")
        assert handoff is not None
        draft = GitHubIssueDraft(
            title=handoff.title,
            body=handoff.body,
            labels=list(handoff.labels),
        )
        issue = self._create_issue(repo, draft)
        control_task = self.tasks.create_task(
            task_type="main_agent_intake",
            agent_id="main-agent",
            status="issue_created",
            user_id=payload.user_id,
            source=payload.source,
            repo=repo,
            issue_number=issue.issue_number,
            title=issue.title,
            external_ref=(
                f"github_issue:{repo}#{issue.issue_number}"
                if issue.issue_number is not None
                else None
            ),
            payload={
                "content": payload.content,
                "issue_url": issue.html_url,
                "labels": issue.labels,
                "entry_agent": "main-agent",
                "next_owner_agent": "ralph",
                "mode": "coding_handoff",
                "handoff": handoff.model_dump(mode="json"),
                "user_session_id": user_session.session_id,
                "agent_session_id": agent_session.session_id,
                "request_id": request_id,
                "run_id": run_id,
                "source_endpoint_id": payload.source_endpoint_id,
                "delivery_endpoint_id": payload.delivery_endpoint_id,
            },
        )
        self.tasks.append_event(
            control_task.task_id,
            "issue_created",
            {
                "issue_number": issue.issue_number,
                "issue_url": issue.html_url,
                "labels": issue.labels,
            },
        )
        self.tasks.append_domain_event(
            control_task.task_id,
            ControlEventType.ISSUE_CREATED,
            {
                "issue_number": issue.issue_number,
                "issue_url": issue.html_url,
                "labels": issue.labels,
            },
        )
        issue_ref = (
            f"Issue #{issue.issue_number}: {self._display_issue_title(issue.title)}"
            if issue.issue_number is not None
            else self._display_issue_title(issue.title)
        )
        self.context.record_short_memory(
            user_session.session_id,
            f"Latest request created {issue_ref}.",
        )
        self.context.record_short_memory(
            agent_session.session_id,
            f"Prepared {issue_ref} for Ralph sleep-coding workflow.",
        )
        notification = self.channel.notify(
            title=f"Ralph 任务开始：{self._display_issue_title(issue.title)}",
            lines=[
                f"来源: Issue #{issue.issue_number or 'n/a'}",
                f"仓库: {repo}",
                f"创建人: {payload.user_id}",
                f"状态: opened | 标签: {', '.join(issue.labels) if issue.labels else 'n/a'}",
                f"Issue: {issue.html_url or 'n/a'}",
                "任务摘要:",
                self._summarize_issue_body(issue.body),
                "Ralph 正在处理中，完成后将自动提交 Pull Request...",
            ],
            endpoint_id=payload.delivery_endpoint_id,
        )
        self.tasks.append_event(
            control_task.task_id,
            "channel_notified",
            {
                "provider": notification.provider,
                "delivered": notification.delivered,
                "is_dry_run": notification.is_dry_run,
                "endpoint_id": notification.endpoint_id,
                "stage": "issue_created",
            },
        )
        issue_ref = (
            f"#{issue.issue_number}"
            if issue.issue_number is not None
            else "dry-run draft"
        )
        return MainAgentIntakeResponse(
            mode="coding_handoff",
            issue=issue,
            message=f"Main Agent created {issue_ref}: {issue.title}",
            chat_response=None,
            handoff=handoff,
            token_usage=usage,
            control_task_id=control_task.task_id,
        )

    def _build_main_agent_output(
        self,
        payload: MainAgentIntakeRequest,
        user_session_id: str,
        *,
        repo: str | None,
    ) -> tuple[str, TokenUsage, str | None, MainAgentCodingHandoff | None]:
        prompt = self.context.build_main_agent_input(user_session_id, payload.content)
        llm_usage: TokenUsage | None = None
        if self.settings.has_runtime_llm_credentials:
            try:
                response = self._generate_issue_draft_with_retry(
                    prompt,
                )
                llm_usage = response.usage
                try:
                    parsed = self._parse_issue_draft_output(response.output_text)
                    mode, chat_response, handoff = self._normalize_main_agent_output(
                        parsed,
                        payload,
                        repo=repo,
                    )
                    return mode, response.usage, chat_response, handoff
                except (json.JSONDecodeError, ValidationError):
                    pass
            except Exception:
                raise
        mode, chat_response, handoff = self._build_heuristic_main_agent_output(payload, repo=repo)
        output_text = (
            chat_response
            if mode == "chat"
            else handoff.model_dump_json()
        )
        usage = self.token_counter.estimate_text_usage(
            provider=self.settings.resolved_llm_default_provider,
            model=self.settings.resolved_llm_default_model,
            input_text=prompt,
            output_text=output_text,
            existing_usage=TokenUsage(),
        )
        if llm_usage is not None:
            return mode, llm_usage, chat_response, handoff
        return mode, usage.model_copy(update={"message_count": 2}), chat_response, handoff

    def _generate_issue_draft_with_retry(self, prompt: str):
        return self.agent_runtime.generate_structured_output(
            self._build_agent_descriptor(),
            user_prompt=prompt,
            workflow="general",
            output_contract=(
                "Return strict JSON. "
                "For chat mode, return keys `mode`=`chat` and `reply`. "
                "For coding mode, return keys `mode`=`coding_handoff` and `handoff`. "
                "`handoff` must contain `title`, `body`, `labels`, `acceptance`, `constraints`, `repo`, and `next_owner_agent`. "
                "The labels array must include `agent:ralph` and `workflow:sleep-coding`. "
                "`next_owner_agent` must be `ralph`."
            ),
        )

    def _parse_issue_draft_output(self, output_text: str) -> dict[str, Any]:
        parsed = parse_structured_object(output_text)
        if not isinstance(parsed, dict):
            raise json.JSONDecodeError("Issue draft output must be an object", output_text, 0)
        return parsed

    def _normalize_main_agent_output(
        self,
        parsed: dict[str, Any],
        payload: MainAgentIntakeRequest,
        *,
        repo: str | None,
    ) -> tuple[str, str | None, MainAgentCodingHandoff | None]:
        raw_mode = parsed.get("mode")
        mode = str(raw_mode).strip() if isinstance(raw_mode, str) and raw_mode.strip() else ""
        if mode == "chat":
            reply = parsed.get("reply") or parsed.get("message")
            if isinstance(reply, str) and reply.strip():
                return "chat", reply.strip(), None
        if mode == "coding_handoff":
            raw_handoff = parsed.get("handoff")
            if isinstance(raw_handoff, dict):
                return "coding_handoff", None, self._normalize_handoff(raw_handoff, payload, repo=repo)
        if {"title", "body", "labels"} <= parsed.keys():
            return "coding_handoff", None, self._normalize_handoff(parsed, payload, repo=repo)
        return self._build_heuristic_main_agent_output(payload, repo=repo)

    def _build_heuristic_main_agent_output(
        self,
        payload: MainAgentIntakeRequest,
        *,
        repo: str | None,
    ) -> tuple[str, str | None, MainAgentCodingHandoff | None]:
        if self._needs_scope_clarification(payload.content):
            reply = (
                "Main Agent needs the request narrowed before opening a coding handoff. "
                "Please split it into 1-2 concrete changes and name the highest-priority main-chain goal."
            )
            return "chat", reply, None
        if self._should_route_to_coding(payload.content):
            draft = self._build_heuristic_issue_draft(payload)
            return "coding_handoff", None, self._normalize_handoff(draft.model_dump(mode="json"), payload, repo=repo)
        reply = (
            "Main Agent kept this request in chat mode and did not open a coding handoff. "
            "If you want code changes, say which behavior or files should change."
        )
        return "chat", reply, None

    def _normalize_handoff(
        self,
        raw: dict[str, Any],
        payload: MainAgentIntakeRequest,
        *,
        repo: str | None,
    ) -> MainAgentCodingHandoff:
        labels = [str(item) for item in raw.get("labels", []) if isinstance(item, str)]
        for required in ("agent:ralph", "workflow:sleep-coding"):
            if required not in labels:
                labels.append(required)
        if "agent:main" not in labels:
            labels.insert(0, "agent:main")
        acceptance = self._coerce_string_list(raw.get("acceptance"))
        if not acceptance:
            acceptance = [
                "Implement the minimum viable change.",
                "Add or update tests for the changed behavior.",
            ]
        constraints = self._coerce_string_list(raw.get("constraints"))
        if not constraints:
            constraints = ["Keep the implementation scoped to the requested change."]
        title = str(raw.get("title", "")).strip() or self._build_heuristic_issue_draft(payload).title
        body = str(raw.get("body", "")).strip() or self._build_heuristic_issue_draft(payload).body
        return MainAgentCodingHandoff(
            title=title,
            body=body,
            labels=labels,
            acceptance=acceptance,
            constraints=constraints,
            repo=repo,
            next_owner_agent="ralph",
        )

    def _should_route_to_coding(self, content: str) -> bool:
        normalized = " ".join(content.strip().lower().split())
        if not normalized:
            return False
        explicit_chat_override_markers = (
            "不要创建 issue",
            "别创建 issue",
            "只解释",
            "不要改代码",
            "不需要改代码",
            "just explain",
        )
        if any(marker in normalized for marker in explicit_chat_override_markers):
            return False
        if self._looks_like_status_or_explanation_request(normalized):
            return False
        strong_coding_markers = (
            "实现",
            "开发",
            "修复",
            "修改",
            "新增",
            "添加",
            "支持",
            "接入",
            "重构",
            "代码",
            "测试",
            "bug",
            "issue",
        )
        weak_coding_markers = (
            "pull request",
            "pr",
            "workflow",
            "接口",
            "功能",
            "需求",
            "github",
            "mcp",
            "错误",
            "报错",
            "链路",
        )
        if any(marker in normalized for marker in strong_coding_markers):
            return True
        return any(marker in normalized for marker in weak_coding_markers)

    def _looks_like_status_or_explanation_request(self, normalized: str) -> bool:
        explanation_markers = (
            "为什么",
            "解释一下",
            "介绍一下",
            "负责什么",
            "是什么",
            "现状",
            "当前状态",
            "进度怎么样",
            "状态怎么样",
            "可用吗",
            "不可用",
        )
        action_markers = ("修复", "实现", "修改", "新增", "添加", "接入", "重构", "补测试")
        return any(marker in normalized for marker in explanation_markers) and not any(
            marker in normalized for marker in action_markers
        )

    def _needs_scope_clarification(self, content: str) -> bool:
        normalized = " ".join(content.strip().lower().split())
        if not normalized:
            return False
        broad_area_markers = ("主链", "rag", "milvus", "监控", "部署", "review", "gateway")
        matched_areas = [marker for marker in broad_area_markers if marker in normalized]
        return len(matched_areas) >= 4 or (
            len(matched_areas) >= 3 and any(marker in normalized for marker in ("全部", "一次性", "全都"))
        )

    def _coerce_string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _create_issue(self, repo: str, draft: GitHubIssueDraft) -> GitHubIssueResult:
        server = self._require_github_server("create_issue")
        result = self.agent_runtime.mcp.call_tool(
            MCPToolCall(
                server=server,
                tool="create_issue",
                arguments={
                    "repo": repo,
                    "title": draft.title,
                    "body": draft.body,
                    "labels": draft.labels,
                },
            )
        )
        return self._coerce_issue_result(result.content, draft)

    def _build_heuristic_issue_draft(
        self,
        payload: MainAgentIntakeRequest,
    ) -> GitHubIssueDraft:
        normalized = " ".join(payload.content.strip().split())
        preview = normalized[:72] if normalized else "Untitled request"
        body = (
            "## User Request\n"
            f"{payload.content.strip() or 'No user content provided.'}\n\n"
            "## Acceptance Notes\n"
            "- Clarify affected modules and interfaces.\n"
            "- Implement the minimum viable change.\n"
            "- Add or update tests for the changed behavior.\n"
        )
        return GitHubIssueDraft(
            title=f"[Main Agent] {preview}",
            body=body,
            labels=[
                "agent:main",
                "agent:ralph",
                "workflow:intake",
                "workflow:sleep-coding",
            ],
        )

    def _build_agent_descriptor(self) -> AgentDescriptor:
        return AgentDescriptor.from_spec(self.settings.resolve_agent_spec("main-agent"))

    def _summarize_issue_body(self, body: str) -> str:
        for line in body.splitlines():
            candidate = line.strip().lstrip("-").strip()
            if not candidate or candidate.startswith("#"):
                continue
            return candidate[:160]
        return "n/a"

    def _display_issue_title(self, title: str) -> str:
        normalized = title.strip()
        if normalized.startswith("[Main Agent] "):
            return normalized[len("[Main Agent] ") :]
        return normalized

    def _require_github_server(self, tool: str) -> str:
        server = self.settings.mcp_github_server_name
        if server not in self.agent_runtime.mcp.available_servers():
            raise RuntimeError(
                f"GitHub MCP server `{server}` is not configured. Define it in {self.settings.resolved_mcp_config_path.name}."
            )
        if not self.agent_runtime.mcp.has_tool(server, tool):
            raise RuntimeError(
                f"GitHub MCP server `{server}` does not expose required tool `{tool}`."
            )
        return server

    def _coerce_issue_result(
        self,
        content: object,
        draft: GitHubIssueDraft,
    ) -> GitHubIssueResult:
        if isinstance(content, GitHubIssueResult):
            return content
        if isinstance(content, dict):
            issue_url = content.get("html_url") or content.get("url")
            issue_number = content.get("issue_number")
            if issue_number is None and isinstance(issue_url, str):
                match = re.search(r"/issues/(?P<number>\d+)$", issue_url)
                if match:
                    issue_number = int(match.group("number"))
            payload = {
                "issue_number": issue_number,
                "title": draft.title,
                "body": draft.body,
                "html_url": issue_url,
                "labels": content.get("labels") or draft.labels,
                "is_dry_run": False,
                **content,
            }
            return GitHubIssueResult.model_validate(payload)
        if isinstance(content, str) and content.strip():
            raise RuntimeError(f"GitHub MCP create_issue failed: {content.strip()}")
        raise ValueError("MCP create_issue result is not a supported payload")
