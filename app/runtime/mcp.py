from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

try:
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.types import CallToolResult, TextContent
except ImportError:  # pragma: no cover - optional dependency path
    anyio = None
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    CallToolResult = None
    TextContent = None

from app.core.config import Settings


@dataclass(frozen=True)
class MCPTool:
    server: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPToolCall:
    server: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPToolResult:
    server: str
    tool: str
    content: Any
    is_error: bool = False


class MCPServerAdapter(Protocol):
    def list_tools(self) -> list[MCPTool]: ...

    def call_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult: ...


@dataclass(frozen=True)
class StdioMCPServerConfig:
    server_name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class MCPServerConfigDefinition:
    server_name: str
    transport: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None
    timeout_seconds: float = 30.0
    adapter: str | None = None


class MCPClient:
    def __init__(self) -> None:
        self._adapters: dict[str, MCPServerAdapter] = {}
        self._tool_cache: dict[str, list[MCPTool]] = {}

    def register_adapter(self, server: str, adapter: MCPServerAdapter) -> None:
        self._adapters[server] = adapter
        self._tool_cache.pop(server, None)

    def list_tools(self, server: str) -> list[MCPTool]:
        cached = self._tool_cache.get(server)
        if cached is not None:
            return list(cached)
        adapter = self._require_adapter(server)
        tools = adapter.list_tools()
        self._tool_cache[server] = list(tools)
        return list(tools)

    def has_tool(self, server: str, tool: str) -> bool:
        return any(candidate.name == tool for candidate in self.list_tools(server))

    def call_tool(self, call: MCPToolCall) -> MCPToolResult:
        adapter = self._require_adapter(call.server)
        return adapter.call_tool(call.tool, call.arguments)

    def available_servers(self) -> list[str]:
        return sorted(self._adapters)

    def _require_adapter(self, server: str) -> MCPServerAdapter:
        adapter = self._adapters.get(server)
        if adapter is None:
            raise ValueError(f"MCP server is not registered: {server}")
        return adapter


class StdioMCPServerAdapter:
    def __init__(self, config: StdioMCPServerConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._runtime: _StdioSessionRuntime | None = None
        self._require_sdk()

    def list_tools(self) -> list[MCPTool]:
        with self._lock:
            runtime = self._ensure_runtime_locked()
            try:
                return runtime.list_tools()
            except BaseException as exc:
                if not self._is_recoverable_session_error(exc):
                    raise
                self._close_runtime_locked()
                return self._ensure_runtime_locked().list_tools()

    def call_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        with self._lock:
            runtime = self._ensure_runtime_locked()
            try:
                return runtime.call_tool(tool, arguments)
            except BaseException as exc:
                if not self._is_recoverable_session_error(exc):
                    raise
                self._close_runtime_locked()
                return self._ensure_runtime_locked().call_tool(tool, arguments)

    def close(self) -> None:
        with self._lock:
            self._close_runtime_locked()

    def _ensure_runtime_locked(self) -> "_StdioSessionRuntime":
        if self._runtime is None:
            self._runtime = _StdioSessionRuntime(self.config)
        return self._runtime

    def _close_runtime_locked(self) -> None:
        if self._runtime is None:
            return
        self._runtime.close()
        self._runtime = None

    def _is_recoverable_session_error(self, exc: BaseException) -> bool:
        if isinstance(exc, BaseExceptionGroup):
            return any(self._is_recoverable_session_error(item) for item in exc.exceptions)
        recoverable_types = (
            anyio.BrokenResourceError,
            anyio.ClosedResourceError,
            anyio.EndOfStream,
        )
        return isinstance(exc, recoverable_types)

    def _require_sdk(self) -> None:
        if (
            anyio is None
            or ClientSession is None
            or StdioServerParameters is None
            or stdio_client is None
        ):
            raise RuntimeError(
                "The `mcp` package is required for stdio MCP adapters. Install project dependencies first."
            )


class _AsyncStdioSession:
    def __init__(self, config: StdioMCPServerConfig) -> None:
        self.config = config

    async def run(self, request_queue: "queue.Queue[_SessionRequest]") -> None:
        params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=self.config.env or None,
            cwd=self.config.cwd,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                while True:
                    request = await anyio.to_thread.run_sync(request_queue.get)
                    if request.kind == "close":
                        request.succeed(None)
                        return
                    try:
                        if request.kind == "list_tools":
                            result = await session.list_tools()
                            request.succeed(_build_mcp_tools(self.config.server_name, result))
                            continue
                        if request.kind == "call_tool":
                            result = await session.call_tool(
                                request.tool,
                                request.arguments,
                                read_timeout_seconds=timedelta(seconds=self.config.timeout_seconds),
                            )
                            request.succeed(
                                MCPToolResult(
                                    server=self.config.server_name,
                                    tool=request.tool,
                                    content=_extract_call_tool_content(result),
                                    is_error=bool(result.isError),
                                )
                            )
                            continue
                        request.fail(RuntimeError(f"Unsupported MCP request kind: {request.kind}"))
                    except BaseException as exc:
                        request.fail(exc)
                        raise


class _StdioSessionRuntime:
    def __init__(self, config: StdioMCPServerConfig) -> None:
        self._config = config
        self._terminal_error: BaseException | None = None
        self._request_queue: queue.Queue[_SessionRequest] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run_session_thread,
            name=f"mcp-session-{config.server_name}",
            daemon=True,
        )
        self._thread.start()

    def list_tools(self) -> list[MCPTool]:
        return self._submit(_SessionRequest(kind="list_tools"))

    def call_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        return self._submit(_SessionRequest(kind="call_tool", tool=tool, arguments=arguments))

    def close(self) -> None:
        if not self._thread.is_alive():
            return
        try:
            self._submit(_SessionRequest(kind="close"), timeout_seconds=5.0)
        except BaseException:
            pass
        self._thread.join(timeout=5.0)

    def _submit(self, request: "_SessionRequest", timeout_seconds: float | None = None) -> Any:
        if not self._thread.is_alive():
            if self._terminal_error is not None:
                raise self._terminal_error
            raise RuntimeError(f"MCP session thread stopped for server `{self._config.server_name}`")
        self._request_queue.put(request)
        return request.await_result(timeout_seconds)

    def _run_session_thread(self) -> None:
        try:
            anyio.run(self._serve)
        except BaseException as exc:
            self._terminal_error = exc

    async def _serve(self) -> None:
        await _AsyncStdioSession(self._config).run(self._request_queue)


@dataclass
class _SessionRequest:
    kind: str
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    _response_queue: "queue.Queue[tuple[bool, Any]]" = field(default_factory=queue.Queue)

    def succeed(self, value: Any) -> None:
        self._response_queue.put((True, value))

    def fail(self, exc: BaseException) -> None:
        self._response_queue.put((False, exc))

    def await_result(self, timeout_seconds: float | None = None) -> Any:
        succeeded, value = self._response_queue.get(timeout=timeout_seconds)
        if not succeeded:
            raise value
        return value


def _extract_call_tool_content(result: CallToolResult) -> Any:
    if result.structuredContent is not None:
        return result.structuredContent
    if len(result.content) == 1 and isinstance(result.content[0], TextContent):
        text = result.content[0].text.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    normalized: list[Any] = []
    for item in result.content:
        if isinstance(item, TextContent):
            normalized.append(item.text)
        elif hasattr(item, "model_dump"):
            normalized.append(item.model_dump(mode="json"))
        else:
            normalized.append(item)
    return normalized


def _build_mcp_tools(server_name: str, result: Any) -> list[MCPTool]:
    return [
        MCPTool(
            server=server_name,
            name=tool.name,
            description=tool.description or "",
            input_schema=tool.inputSchema or {},
        )
        for tool in result.tools
    ]


class GitHubMCPAdapter:
    def __init__(self, server: str, base_adapter: MCPServerAdapter) -> None:
        self.server = server
        self.base = base_adapter
        self._tool_specs = {
            "get_issue": MCPTool(
                server=server,
                name="get_issue",
                description="Read a GitHub issue by repo and issue number.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "issue_number": {"type": "integer"},
                    },
                    "required": ["repo", "issue_number"],
                },
            ),
            "create_issue": MCPTool(
                server=server,
                name="create_issue",
                description="Create a GitHub issue with title, body, and labels.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["repo", "title", "body"],
                },
            ),
            "create_issue_comment": MCPTool(
                server=server,
                name="create_issue_comment",
                description="Add a comment to an issue or pull request.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "issue_number": {"type": "integer"},
                        "body": {"type": "string"},
                    },
                    "required": ["repo", "issue_number", "body"],
                },
            ),
            "list_issues": MCPTool(
                server=server,
                name="list_issues",
                description="List GitHub issues for a repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "state": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["repo"],
                },
            ),
            "apply_labels": MCPTool(
                server=server,
                name="apply_labels",
                description="Set labels on a GitHub issue or pull request number.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "issue_number": {"type": "integer"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["repo", "issue_number", "labels"],
                },
            ),
            "create_pull_request": MCPTool(
                server=server,
                name="create_pull_request",
                description="Create a pull request from head to base branch.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "head_branch": {"type": "string"},
                        "base_branch": {"type": "string"},
                    },
                    "required": ["repo", "title", "body", "head_branch", "base_branch"],
                },
            ),
            "create_branch": MCPTool(
                server=server,
                name="create_branch",
                description="Create a Git branch from an existing base branch.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "branch": {"type": "string"},
                        "from_branch": {"type": "string"},
                    },
                    "required": ["repo", "branch"],
                },
            ),
            "create_or_update_file": MCPTool(
                server=server,
                name="create_or_update_file",
                description="Create or update a single file in a branch.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "branch": {"type": "string"},
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "message": {"type": "string"},
                        "sha": {"type": "string"},
                    },
                    "required": ["repo", "branch", "path", "content", "message"],
                },
            ),
            "push_files": MCPTool(
                server=server,
                name="push_files",
                description="Commit multiple file updates to a branch.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "branch": {"type": "string"},
                        "files": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["path", "content"],
                            },
                        },
                        "message": {"type": "string"},
                    },
                    "required": ["repo", "branch", "files", "message"],
                },
            ),
            "pull_request_review_write": MCPTool(
                server=server,
                name="pull_request_review_write",
                description="Create or submit a GitHub pull request review.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "pr_number": {"type": "integer"},
                        "method": {"type": "string"},
                        "event": {"type": "string"},
                        "body": {"type": "string"},
                        "commit_id": {"type": "string"},
                    },
                    "required": ["repo", "pr_number", "method"],
                },
            ),
            "get_file_contents": MCPTool(
                server=server,
                name="get_file_contents",
                description="Get file contents for a branch or commit.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "path": {"type": "string"},
                        "ref": {"type": "string"},
                        "sha": {"type": "string"},
                    },
                    "required": ["repo"],
                },
            ),
        }

    def list_tools(self) -> list[MCPTool]:
        available = {tool.name for tool in self.base.list_tools()}
        mapping = {
            "get_issue": "issue_read",
            "create_issue": "issue_write",
            "create_issue_comment": "add_issue_comment",
            "list_issues": "list_issues",
            "apply_labels": "issue_write",
            "create_pull_request": "create_pull_request",
            "create_branch": "create_branch",
            "create_or_update_file": "create_or_update_file",
            "push_files": "push_files",
            "pull_request_review_write": "pull_request_review_write",
            "get_file_contents": "get_file_contents",
        }
        return [
            tool
            for alias, tool in self._tool_specs.items()
            if mapping[alias] in available
        ]

    def call_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        owner, repo = self._split_repo(arguments["repo"])
        if tool == "get_issue":
            return self.base.call_tool(
                "issue_read",
                {
                    "owner": owner,
                    "repo": repo,
                    "issue_number": arguments["issue_number"],
                    "method": "get",
                },
            )
        if tool == "create_issue":
            payload = {
                "owner": owner,
                "repo": repo,
                "method": "create",
                "title": arguments["title"],
                "body": arguments["body"],
            }
            labels = arguments.get("labels")
            if labels:
                payload["labels"] = labels
            return self.base.call_tool("issue_write", payload)
        if tool == "create_issue_comment":
            return self.base.call_tool(
                "add_issue_comment",
                {
                    "owner": owner,
                    "repo": repo,
                    "issue_number": arguments["issue_number"],
                    "body": arguments["body"],
                },
            )
        if tool == "list_issues":
            return self.base.call_tool(
                "list_issues",
                {
                    "owner": owner,
                    "repo": repo,
                    "state": arguments.get("state", "open"),
                    "perPage": arguments.get("limit", 20),
                },
            )
        if tool == "apply_labels":
            return self.base.call_tool(
                "issue_write",
                {
                    "owner": owner,
                    "repo": repo,
                    "method": "update",
                    "issue_number": arguments["issue_number"],
                    "labels": arguments.get("labels", []),
                },
            )
        if tool == "create_pull_request":
            return self.base.call_tool(
                "create_pull_request",
                {
                    "owner": owner,
                    "repo": repo,
                    "title": arguments["title"],
                    "body": arguments["body"],
                    "head": arguments["head_branch"],
                    "base": arguments["base_branch"],
                },
            )
        if tool == "create_branch":
            payload = {
                "owner": owner,
                "repo": repo,
                "branch": arguments["branch"],
            }
            if arguments.get("from_branch"):
                payload["from_branch"] = arguments["from_branch"]
            return self.base.call_tool("create_branch", payload)
        if tool == "create_or_update_file":
            payload = {
                "owner": owner,
                "repo": repo,
                "branch": arguments["branch"],
                "path": arguments["path"],
                "content": arguments["content"],
                "message": arguments["message"],
            }
            if arguments.get("sha"):
                payload["sha"] = arguments["sha"]
            return self.base.call_tool("create_or_update_file", payload)
        if tool == "push_files":
            return self.base.call_tool(
                "push_files",
                {
                    "owner": owner,
                    "repo": repo,
                    "branch": arguments["branch"],
                    "files": arguments["files"],
                    "message": arguments["message"],
                },
            )
        if tool == "pull_request_review_write":
            payload = {
                "owner": owner,
                "repo": repo,
                "pullNumber": arguments["pr_number"],
                "method": arguments["method"],
            }
            if arguments.get("event"):
                payload["event"] = arguments["event"]
            if arguments.get("body"):
                payload["body"] = arguments["body"]
            if arguments.get("commit_id"):
                payload["commitID"] = arguments["commit_id"]
            return self.base.call_tool("pull_request_review_write", payload)
        if tool == "get_file_contents":
            payload = {
                "owner": owner,
                "repo": repo,
            }
            if arguments.get("path"):
                payload["path"] = arguments["path"]
            if arguments.get("ref"):
                payload["ref"] = arguments["ref"]
            if arguments.get("sha"):
                payload["sha"] = arguments["sha"]
            return self.base.call_tool("get_file_contents", payload)
        raise ValueError(f"Unsupported GitHub MCP tool alias: {tool}")

    def _split_repo(self, repo: str) -> tuple[str, str]:
        owner, separator, name = repo.partition("/")
        if not separator or not owner or not name:
            raise ValueError(f"GitHub repo must use owner/name format: {repo}")
        return owner, name


class InMemoryMCPServer:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[MCPTool, Any]] = {}

    def register_tool(
        self,
        name: str,
        handler: Any,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        *,
        server: str = "in-memory",
    ) -> None:
        self._tools[name] = (
            MCPTool(
                server=server,
                name=name,
                description=description,
                input_schema=input_schema or {},
            ),
            handler,
        )

    def list_tools(self) -> list[MCPTool]:
        return [tool for tool, _ in self._tools.values()]

    def call_tool(self, tool: str, arguments: dict[str, Any]) -> MCPToolResult:
        entry = self._tools.get(tool)
        if entry is None:
            raise ValueError(f"MCP tool is not registered: {tool}")
        tool_def, handler = entry
        content = handler(arguments)
        return MCPToolResult(server=tool_def.server, tool=tool, content=content)


def load_mcp_server_definitions(settings: Settings) -> list[MCPServerConfigDefinition]:
    return _load_mcp_server_definitions_from_file(settings)


def get_mcp_server_definition(
    settings: Settings,
    server_name: str,
) -> MCPServerConfigDefinition | None:
    for definition in load_mcp_server_definitions(settings):
        if definition.server_name == server_name:
            return definition
    return None


def _load_mcp_server_definitions_from_file(
    settings: Settings,
) -> list[MCPServerConfigDefinition]:
    config_path = settings.resolved_mcp_config_path
    if not config_path.exists():
        return []
    loaded = json.loads(config_path.read_text(encoding="utf-8"))
    servers = loaded.get("servers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcp.json `servers` must be an object")
    definitions: list[MCPServerConfigDefinition] = []
    placeholder_context = _build_placeholder_context(settings)
    for server_name, raw in servers.items():
        if not isinstance(raw, dict):
            raise ValueError(f"mcp.json server config must be an object: {server_name}")
        transport = str(raw.get("transport", "stdio")).strip()
        if transport != "stdio":
            raise ValueError(f"Unsupported MCP transport for server {server_name}: {transport}")
        command = str(raw.get("command", "")).strip()
        if not command:
            raise ValueError(f"mcp.json server is missing command: {server_name}")
        args = raw.get("args", [])
        if not isinstance(args, list):
            raise ValueError(f"mcp.json server args must be a list: {server_name}")
        env = raw.get("env", {})
        if env is None:
            env = {}
        if not isinstance(env, dict):
            raise ValueError(f"mcp.json server env must be an object: {server_name}")
        cwd_value = raw.get("cwd")
        cwd = _resolve_optional_path(settings.project_root, cwd_value)
        timeout_seconds = float(raw.get("timeout_seconds", settings.mcp_request_timeout_seconds))
        adapter = raw.get("adapter")
        definitions.append(
            MCPServerConfigDefinition(
                server_name=str(server_name),
                transport=transport,
                command=command,
                args=[_resolve_env_placeholders(str(item), placeholder_context) for item in args],
                env={
                    str(key): _resolve_env_placeholders(str(value), placeholder_context)
                    for key, value in env.items()
                },
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                adapter=str(adapter) if adapter is not None else None,
            )
        )
    return definitions

def _build_placeholder_context(settings: Settings) -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if isinstance(value, str)
    }


def _resolve_env_placeholders(raw: str, placeholder_context: dict[str, str]) -> str:
    resolved = raw
    for key, value in placeholder_context.items():
        resolved = resolved.replace(f"${{{key}}}", value)
    return resolved


def _resolve_optional_path(project_root: Path, raw: Any) -> Path | None:
    if raw in {None, ""}:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.is_absolute() else project_root / path


def build_default_mcp_client(settings: Settings) -> MCPClient:
    client = MCPClient()
    if settings.app_env == "test":
        return client
    for definition in load_mcp_server_definitions(settings):
        config = StdioMCPServerConfig(
            server_name=definition.server_name,
            command=definition.command,
            args=definition.args,
            env=definition.env,
            cwd=definition.cwd,
            timeout_seconds=definition.timeout_seconds,
        )
        base_adapter = StdioMCPServerAdapter(config)
        adapter: MCPServerAdapter = base_adapter
        if definition.adapter == "github":
            adapter = GitHubMCPAdapter(
                server=definition.server_name,
                base_adapter=base_adapter,
            )
        client.register_adapter(definition.server_name, adapter)
    return client
