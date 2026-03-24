from __future__ import annotations

from app.core.config import Settings
from app.models.schemas import ChannelEndpoint, ConversationRoute, EndpointBinding


class ChannelEndpointRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._endpoints, self._bindings = self._load()

    def list_endpoints(self) -> dict[str, ChannelEndpoint]:
        return dict(self._endpoints)

    def get_endpoint(self, endpoint_id: str | None) -> ChannelEndpoint:
        if endpoint_id and endpoint_id in self._endpoints:
            return self._endpoints[endpoint_id]
        return self._default_endpoint()

    def resolve_endpoint_id(
        self,
        *,
        endpoint_id: str | None = None,
        provider: str | None = None,
        external_ref: str | None = None,
        external_refs: list[str] | None = None,
    ) -> str:
        if endpoint_id and endpoint_id in self._endpoints:
            candidate = self._endpoints[endpoint_id]
            if candidate.entry_enabled:
                return endpoint_id
        candidate_refs: list[str] = []
        if isinstance(external_refs, list):
            candidate_refs.extend(
                value.strip()
                for value in external_refs
                if isinstance(value, str) and value.strip()
            )
        if external_ref:
            candidate_refs.append(external_ref)
        if candidate_refs:
            for candidate in self._endpoints.values():
                if provider and candidate.provider != provider:
                    continue
                if not candidate.entry_enabled:
                    continue
                if any(ref in candidate.external_refs for ref in candidate_refs):
                    return candidate.endpoint_id
        configured_default = self._channel_config().get("default_endpoint")
        if (
            isinstance(configured_default, str)
            and configured_default in self._endpoints
            and self._endpoints[configured_default].entry_enabled
        ):
            return configured_default
        return self._default_endpoint().endpoint_id

    def resolve_binding(self, endpoint_id: str | None) -> EndpointBinding:
        if endpoint_id and endpoint_id in self._bindings:
            return self._bindings[endpoint_id]
        return EndpointBinding(endpoint_id="default")

    def resolve_delivery_endpoint_id(
        self,
        *,
        source_endpoint_id: str,
        workflow: str,
    ) -> str:
        binding = self.resolve_binding(source_endpoint_id)
        policy = binding.delivery_policy or {"mode": "same_endpoint"}
        mode = str(policy.get("mode", "same_endpoint")).strip() or "same_endpoint"
        delivery_endpoint_id = source_endpoint_id
        if mode == "fixed_endpoint":
            candidate = policy.get("endpoint_id") or policy.get("fixed_endpoint_id")
            if isinstance(candidate, str) and candidate.strip():
                delivery_endpoint_id = candidate.strip()
        elif mode == "workflow_mapped":
            workflow_endpoints = policy.get("workflow_endpoints")
            if isinstance(workflow_endpoints, dict):
                candidate = workflow_endpoints.get(workflow)
                if isinstance(candidate, str) and candidate.strip() and candidate != "same_endpoint":
                    delivery_endpoint_id = candidate.strip()
        endpoint = self._endpoints.get(delivery_endpoint_id)
        if endpoint is None or not endpoint.delivery_enabled:
            return source_endpoint_id
        return delivery_endpoint_id

    def resolve_conversation_route(
        self,
        *,
        endpoint_id: str,
        workflow: str,
        active_agent: str,
        session_id: str,
    ) -> ConversationRoute:
        return ConversationRoute(
            session_id=session_id,
            source_endpoint_id=endpoint_id,
            active_agent=active_agent,
            active_workflow=workflow,
            delivery_endpoint_id=self.resolve_delivery_endpoint_id(
                source_endpoint_id=endpoint_id,
                workflow=workflow,
            ),
        )

    def _load(self) -> tuple[dict[str, ChannelEndpoint], dict[str, EndpointBinding]]:
        channel = self._channel_config()
        raw_endpoints = channel.get("endpoints")
        if not isinstance(raw_endpoints, dict) or not raw_endpoints:
            default = self._default_endpoint()
            return (
                {default.endpoint_id: default},
                {default.endpoint_id: EndpointBinding(endpoint_id=default.endpoint_id)},
            )
        endpoints: dict[str, ChannelEndpoint] = {}
        bindings: dict[str, EndpointBinding] = {}
        for endpoint_id, raw in raw_endpoints.items():
            if not isinstance(endpoint_id, str) or not isinstance(raw, dict):
                continue
            endpoint = ChannelEndpoint(
                endpoint_id=endpoint_id,
                provider=str(raw.get("provider", self.settings.resolved_channel_provider)),
                mode=str(raw.get("mode", "primary")),
                entry_enabled=bool(raw.get("entry_enabled", True)),
                delivery_enabled=bool(raw.get("delivery_enabled", True)),
                webhook_url=(
                    str(raw["webhook_url"]).strip()
                    if isinstance(raw.get("webhook_url"), str) and str(raw.get("webhook_url")).strip()
                    else None
                ),
                external_refs=[
                    str(value).strip()
                    for value in raw.get("external_refs", [])
                    if isinstance(value, str) and value.strip()
                ],
            )
            endpoints[endpoint_id] = endpoint
            bindings[endpoint_id] = EndpointBinding(
                endpoint_id=endpoint_id,
                default_agent=str(raw.get("default_agent", "main-agent")),
                default_workflow=str(raw.get("default_workflow", "general")),
                delivery_policy=raw.get("delivery_policy")
                if isinstance(raw.get("delivery_policy"), dict)
                else {"mode": str(raw.get("delivery_policy", "same_endpoint"))},
                allowed_handoffs=[
                    str(value).strip()
                    for value in raw.get("allowed_handoffs", [])
                    if isinstance(value, str) and value.strip()
                ],
            )
        if not endpoints:
            default = self._default_endpoint()
            return (
                {default.endpoint_id: default},
                {default.endpoint_id: EndpointBinding(endpoint_id=default.endpoint_id)},
            )
        return endpoints, bindings

    def _channel_config(self) -> dict[str, object]:
        raw = self.settings.platform_config.get("channel", {})
        return raw if isinstance(raw, dict) else {}

    def _default_endpoint(self) -> ChannelEndpoint:
        return ChannelEndpoint(
            endpoint_id="default",
            provider=self.settings.resolved_channel_provider,
            mode="primary",
            entry_enabled=True,
            delivery_enabled=True,
        )
