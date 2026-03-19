from __future__ import annotations

from shutil import which
from typing import Any

from app.core.config import Settings, get_settings
from app.runtime.mcp import build_default_mcp_client, load_mcp_server_definitions


class IntegrationDiagnosticsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_report(self) -> dict[str, Any]:
        return {
            "github_mcp": self._github_mcp_status(),
            "ralph_execution": self._ralph_execution_status(),
            "review_skill": self._review_skill_status(),
            "feishu": self._feishu_status(),
        }

    def _github_mcp_status(self) -> dict[str, Any]:
        definitions = {
            definition.server_name: definition
            for definition in load_mcp_server_definitions(self.settings)
        }
        if self.settings.mcp_github_server_name not in definitions:
            return {
                "status": "not_configured",
                "detail": (
                    f"Server `{self.settings.mcp_github_server_name}` is not defined in "
                    f"{self.settings.resolved_mcp_config_path.name}. GitHub integration is MCP-only."
                ),
            }
        try:
            client = build_default_mcp_client(self.settings)
            tools = [tool.name for tool in client.list_tools(self.settings.mcp_github_server_name)]
            return {
                "status": "ok",
                "server": self.settings.mcp_github_server_name,
                "config_source": (
                    str(self.settings.resolved_mcp_config_path)
                    if self.settings.resolved_mcp_config_path.exists()
                    else "not_configured"
                ),
                "tools": tools,
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    def _review_skill_status(self) -> dict[str, Any]:
        if self.settings.resolved_review_skill_command:
            command = self.settings.resolved_review_skill_command.split()[0]
            if which(command) is None:
                return {"status": "error", "detail": f"Command not found: {command}"}
            return {"status": "ok", "mode": "command", "command": self.settings.resolved_review_skill_command}
        if self.settings.openai_api_key or self.settings.minimax_api_key:
            return {"status": "ok", "mode": "runtime_llm"}
        if which("opencode") is not None:
            return {"status": "ok", "mode": "opencode_fallback"}
        return {"status": "not_configured", "detail": "No review skill command or model credentials configured"}

    def _ralph_execution_status(self) -> dict[str, Any]:
        if self.settings.resolved_sleep_coding_execution_command:
            command = self.settings.resolved_sleep_coding_execution_command.split()[0]
            if which(command) is None:
                return {"status": "error", "detail": f"Command not found: {command}"}
            return {
                "status": "ok",
                "mode": "command",
                "command": self.settings.resolved_sleep_coding_execution_command,
            }
        if self.settings.resolved_sleep_coding_execution_allow_llm_fallback:
            if self.settings.openai_api_key or self.settings.minimax_api_key:
                return {"status": "ok", "mode": "runtime_llm_fallback"}
            return {
                "status": "error",
                "detail": "LLM fallback is enabled but no model credentials are configured",
            }
        return {
            "status": "error",
            "detail": "No local coding command configured. Define `sleep_coding.execution.command` or explicitly enable LLM fallback.",
        }

    def _feishu_status(self) -> dict[str, Any]:
        inbound_ready = bool(
            self.settings.feishu_verification_token or self.settings.feishu_encrypt_key
        )
        outbound_ready = bool(self.settings.channel_webhook_url)
        if inbound_ready and outbound_ready:
            return {"status": "ok", "inbound": True, "outbound": True}
        if inbound_ready or outbound_ready:
            return {
                "status": "partial",
                "inbound": inbound_ready,
                "outbound": outbound_ready,
            }
        return {"status": "not_configured", "inbound": False, "outbound": False}
