from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.runtime.mcp import build_default_mcp_client, load_mcp_server_definitions


class IntegrationDiagnosticsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_report(self) -> dict[str, Any]:
        gateway = self._annotate_component(
            "gateway",
            self._gateway_status(),
            main_chain_requirement="degraded_ok",
            live_requirement="degraded_ok",
        )
        github = self._annotate_component(
            "github_mcp",
            self._github_mcp_status(),
            main_chain_requirement="required",
            live_requirement="required",
        )
        ralph = self._annotate_component(
            "ralph_execution",
            self._ralph_execution_status(),
            main_chain_requirement="required",
            live_requirement="required",
        )
        review = self._annotate_component(
            "review_skill",
            self._review_skill_status(),
            main_chain_requirement="required",
            live_requirement="required",
        )
        channel_delivery = self._annotate_component(
            "channel_delivery",
            self._channel_delivery_status(),
            main_chain_requirement="degraded_ok",
            live_requirement="degraded_ok",
        )
        feishu = self._annotate_component(
            "feishu",
            self._feishu_status(),
            main_chain_requirement="degraded_ok",
            live_requirement="required",
        )
        return {
            "gateway": gateway,
            "github_mcp": github,
            "ralph_execution": ralph,
            "review_skill": review,
            "channel_delivery": channel_delivery,
            "feishu": feishu,
            "main_chain": self._main_chain_status(
                gateway=gateway,
                github=github,
                ralph=ralph,
                review=review,
                channel_delivery=channel_delivery,
                feishu=feishu,
            ),
        }

    def get_live_readiness(self) -> dict[str, Any]:
        main_chain = self.get_report()["main_chain"]
        return {
            "ready": bool(main_chain.get("live_ready")),
            "blocking_components": list(main_chain.get("live_blocking_components", [])),
            "next_action": main_chain.get("next_action"),
            "summary": main_chain.get("acceptance_summary"),
        }

    def _gateway_status(self) -> dict[str, Any]:
        if self.settings.feishu_verification_token or self.settings.feishu_encrypt_key:
            return {"status": "ok", "entry_modes": ["feishu_webhook"]}
        return {
            "status": "partial",
            "detail": "No inbound webhook credentials configured. Manual/API entry remains available.",
            "entry_modes": ["manual_api"],
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
        if self.settings.has_runtime_llm_credentials:
            return {"status": "ok", "mode": "runtime_llm"}
        return {
            "status": "not_configured",
            "detail": "Builtin code-review-agent runtime is unavailable: missing model credentials.",
        }

    def _ralph_execution_status(self) -> dict[str, Any]:
        if self.settings.has_runtime_llm_credentials:
            return {"status": "ok", "mode": "runtime_llm"}
        return {
            "status": "error",
            "detail": "Builtin Ralph runtime is unavailable: missing model credentials.",
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

    def _channel_delivery_status(self) -> dict[str, Any]:
        if self.settings.channel_webhook_url:
            return {"status": "ok", "provider": self.settings.channel_provider or "feishu"}
        return {
            "status": "partial",
            "provider": self.settings.channel_provider or "feishu",
            "detail": "No outbound channel webhook configured. Final delivery falls back to dry-run/local observation.",
        }

    def _main_chain_status(
        self,
        *,
        gateway: dict[str, Any],
        github: dict[str, Any],
        ralph: dict[str, Any],
        review: dict[str, Any],
        channel_delivery: dict[str, Any],
        feishu: dict[str, Any],
    ) -> dict[str, Any]:
        component_statuses = {
            "gateway": gateway,
            "github_mcp": github,
            "ralph_execution": ralph,
            "review_skill": review,
            "channel_delivery": channel_delivery,
            "feishu": feishu,
        }
        blocking_components = [
            name
            for name, status in component_statuses.items()
            if status.get("severity") == "blocking"
        ]
        degraded_components = [
            name
            for name, status in component_statuses.items()
            if status.get("severity") == "degraded"
        ]
        ready = not blocking_components
        live_blocking_components = [
            name for name, status in component_statuses.items() if not status.get("live_ready", False)
        ]
        live_ready = not live_blocking_components
        next_action = None
        if blocking_components:
            next_action = f"repair_{blocking_components[0]}"
        elif live_blocking_components:
            next_action = f"repair_{live_blocking_components[0]}"
        elif degraded_components:
            next_action = f"improve_{degraded_components[0]}"
        return {
            "ready": ready,
            "status": "ready" if ready else "blocked",
            "blocking_components": blocking_components,
            "degraded_components": degraded_components,
            "live_ready": live_ready,
            "live_blocking_components": live_blocking_components,
            "acceptance_status": "ready" if live_ready else "blocked",
            "acceptance_summary": self._build_acceptance_summary(
                live_ready=live_ready,
                live_blocking_components=live_blocking_components,
            ),
            "next_action": next_action,
            "operator_hint": self._build_operator_hint(
                blocking_components=blocking_components,
                degraded_components=degraded_components,
            ),
        }

    def _annotate_component(
        self,
        component: str,
        status: dict[str, Any],
        *,
        main_chain_requirement: str,
        live_requirement: str,
    ) -> dict[str, Any]:
        normalized = dict(status)
        state = str(normalized.get("status", "unknown"))
        severity = "ready"
        if state in {"error", "blocked"}:
            severity = "blocking"
        elif state in {"partial", "not_configured"}:
            severity = "degraded"
        if main_chain_requirement == "required" and state != "ok":
            severity = "blocking"
        normalized["ready"] = state == "ok"
        normalized["severity"] = severity
        normalized["required_for_live_chain"] = live_requirement in {"required", "degraded_ok"}
        normalized["live_ready"] = state == "ok" if live_requirement == "required" else True
        normalized["next_action"] = self._component_next_action(component, severity)
        return normalized

    def _component_next_action(self, component: str, severity: str) -> str | None:
        if severity == "blocking":
            return f"repair_{component}"
        if severity == "degraded":
            return f"improve_{component}"
        return None

    def _build_operator_hint(
        self,
        *,
        blocking_components: list[str],
        degraded_components: list[str],
    ) -> str:
        if blocking_components:
            return f"Fix blocking component `{blocking_components[0]}` first."
        if degraded_components:
            return f"Chain is runnable, but review degraded component `{degraded_components[0]}` next."
        return "Main chain prerequisites are ready."

    def _build_acceptance_summary(
        self,
        *,
        live_ready: bool,
        live_blocking_components: list[str],
    ) -> str:
        if live_ready:
            return "Live chain ready: all required components are healthy."
        return "Live chain blocked: " + ", ".join(live_blocking_components) + "."
