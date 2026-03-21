import json
from dataclasses import dataclass
from functools import cached_property
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    workspace: Path
    skills: list[str]
    mcp_servers: list[str]
    model_profile: str | None
    system_instruction: str
    memory_policy: str
    execution_policy: str


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "marten"
    app_port: int = 8000
    app_data_dir: str = "data"
    langsmith_api_key: str | None = None
    langsmith_project: str = "marten"
    langsmith_tracing: bool = False
    openai_api_key: str | None = None
    openai_api_base: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    minimax_api_key: str | None = None
    minimax_api_base: str = "https://api.minimax.io/v1"
    minimax_model: str = "MiniMax-M2.5"
    llm_default_provider: str = "openai"
    llm_default_model: str | None = None
    llm_request_timeout_seconds: float = 30.0
    llm_request_max_attempts: int = 3
    llm_request_retry_base_delay_seconds: float = 1.0
    minimax_usd_per_cny: float = 0.14
    platform_config_path: str = "platform.json"
    agents_config_path: str = "agents.json"
    models_config_path: str = "models.json"
    skills_root_dir: str = "skills"
    main_agent_workspace: str = "agents/main-agent"
    main_agent_skills: str = "issue-writer"
    main_agent_mcp_servers: str = "github"
    sleep_coding_workspace: str = "agents/ralph"
    sleep_coding_skills: str = "coding-planner,coding-executor"
    sleep_coding_mcp_servers: str = "github"
    mcp_config_path: str = "mcp.json"
    mcp_github_server_name: str = "github"
    mcp_request_timeout_seconds: float = 30.0
    database_url: str = "sqlite:///data/youmeng_gateway.db"
    github_token: str | None = None
    github_api_base: str = "https://api.github.com"
    github_repository: str = "your-org/marten"
    channel_provider: str = "feishu"
    channel_webhook_url: str | None = None
    feishu_verification_token: str | None = None
    feishu_encrypt_key: str | None = None
    sleep_coding_labels: str = "agent:ralph,workflow:sleep-coding"
    sleep_coding_worker_poll_labels: str = "agent:ralph,workflow:sleep-coding"
    sleep_coding_worker_auto_approve_plan: bool = False
    sleep_coding_worker_poll_interval_seconds: int = 300
    sleep_coding_worker_lease_seconds: int = 600
    sleep_coding_worker_heartbeat_timeout_seconds: int = 900
    sleep_coding_worker_max_retries: int = 3
    sleep_coding_worker_retry_backoff_seconds: int = 60
    sleep_coding_scheduler_enabled: bool = False
    review_max_repair_rounds: int = 3
    sleep_coding_worktree_root: str = ".worktrees"
    sleep_coding_enable_git_commit: bool = False
    sleep_coding_enable_git_push: bool = False
    git_remote_name: str = "origin"
    sleep_coding_validation_command: str = "python scripts/run_sleep_coding_validation.py"
    sleep_coding_execution_command: str | None = None
    sleep_coding_execution_allow_llm_fallback: bool = True
    sleep_coding_execution_timeout_seconds: float = 600.0
    sleep_coding_validation_timeout_seconds: float = 600.0
    review_runs_dir: str = "data/review-runs"
    review_workspace: str = "agents/code-review-agent"
    review_skills: str = "code-review"
    review_mcp_servers: str = "github"
    review_skill_name: str = "code-review"
    review_skill_command: str | None = None
    review_command_timeout_seconds: float = 600.0
    review_force_blocking_first_pass: bool = False
    review_writeback_final_only: bool = True
    review_follow_up_delay_seconds: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def resolved_data_dir(self) -> Path:
        return self._resolve_project_path(self.app_data_dir)

    @property
    def resolved_database_path(self) -> Path:
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            database_path = Path(self.database_url.removeprefix(prefix)).expanduser()
            return (
                database_path
                if database_path.is_absolute()
                else self.project_root / database_path
            )
        return self.resolved_data_dir / "youmeng_gateway.db"

    @property
    def resolved_sleep_coding_labels(self) -> list[str]:
        return self._resolve_string_list(
            self._get_platform_setting(
                ("sleep_coding", "labels"),
                self.sleep_coding_labels,
            )
        )

    @property
    def resolved_sleep_coding_worker_poll_labels(self) -> list[str]:
        return self._resolve_string_list(
            self._get_platform_setting(
                ("sleep_coding", "worker", "poll_labels"),
                self.sleep_coding_worker_poll_labels,
            )
        )

    @property
    def resolved_sleep_coding_worktree_root(self) -> Path:
        raw = self._get_platform_setting(
            ("sleep_coding", "git", "worktree_root"),
            self.sleep_coding_worktree_root,
        )
        root = Path(str(raw)).expanduser()
        return root if root.is_absolute() else self.project_root / root

    @property
    def resolved_review_runs_dir(self) -> Path:
        return self._resolve_project_path(self.review_runs_dir)

    @property
    def resolved_sleep_coding_execution_command(self) -> str | None:
        value = self._get_platform_setting(
            ("sleep_coding", "execution", "command"),
            self.sleep_coding_execution_command,
        )
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def resolved_sleep_coding_execution_allow_llm_fallback(self) -> bool:
        return self._resolve_platform_bool(
            ("sleep_coding", "execution", "allow_llm_fallback"),
            self.sleep_coding_execution_allow_llm_fallback,
        )

    @property
    def resolved_sleep_coding_execution_timeout_seconds(self) -> float:
        value = self._get_platform_setting(
            ("sleep_coding", "execution", "timeout_seconds"),
            self.sleep_coding_execution_timeout_seconds,
        )
        return max(float(value), 1.0)

    @property
    def resolved_review_force_blocking_first_pass(self) -> bool:
        return self._resolve_platform_bool(
            ("review", "force_blocking_first_pass"),
            self.review_force_blocking_first_pass,
        )

    @property
    def resolved_review_command_timeout_seconds(self) -> float:
        value = self._get_platform_setting(
            ("review", "command_timeout_seconds"),
            self.review_command_timeout_seconds,
        )
        return max(float(value), 1.0)

    @property
    def resolved_review_writeback_final_only(self) -> bool:
        return bool(
            self._get_platform_setting(
                ("review", "writeback_final_only"),
                self.review_writeback_final_only,
            )
        )

    @property
    def resolved_review_follow_up_delay_seconds(self) -> int:
        value = self._get_platform_setting(
            ("review", "follow_up_delay_seconds"),
            self.review_follow_up_delay_seconds,
        )
        return max(int(value), 0)

    @property
    def resolved_github_repository(self) -> str:
        value = self._get_platform_setting(
            ("github", "repository"),
            self.github_repository,
        )
        return str(value).strip()

    @property
    def resolved_channel_provider(self) -> str:
        value = self._get_platform_setting(
            ("channel", "provider"),
            self.channel_provider,
        )
        return str(value).strip()

    @property
    def resolved_platform_config_path(self) -> Path:
        return self._resolve_project_path(self.platform_config_path)

    @property
    def resolved_agents_config_path(self) -> Path:
        return self._resolve_project_path(self.agents_config_path)

    @property
    def resolved_models_config_path(self) -> Path:
        return self._resolve_project_path(self.models_config_path)

    @cached_property
    def platform_config(self) -> dict[str, object]:
        return self._load_json_config(self.resolved_platform_config_path)

    @cached_property
    def agents_config(self) -> dict[str, object]:
        return self._load_json_config(self.resolved_agents_config_path)

    @cached_property
    def models_config(self) -> dict[str, object]:
        return self._load_json_config(self.resolved_models_config_path)

    @property
    def resolved_skills_root_dir(self) -> Path:
        return self._resolve_project_path(self.skills_root_dir)

    @property
    def resolved_main_agent_workspace(self) -> Path:
        return self._resolve_workspace_path(
            self._get_agent_setting("main-agent", "workspace", self.main_agent_workspace)
        )

    @property
    def resolved_main_agent_skills(self) -> list[str]:
        return self._resolve_string_list(
            self._get_agent_setting("main-agent", "skills", self.main_agent_skills)
        )

    @property
    def resolved_main_agent_mcp_servers(self) -> list[str]:
        return self._resolve_string_list(
            self._get_agent_setting("main-agent", "mcp_servers", self.main_agent_mcp_servers)
        )

    @property
    def resolved_main_agent_model_profile(self) -> str | None:
        return self._get_agent_setting("main-agent", "model_profile", None)

    @property
    def resolved_sleep_coding_workspace(self) -> Path:
        return self._resolve_workspace_path(
            self._get_agent_setting(
                "ralph",
                "workspace",
                self.sleep_coding_workspace,
            )
        )

    @property
    def resolved_sleep_coding_skills(self) -> list[str]:
        return self._resolve_string_list(
            self._get_agent_setting(
                "ralph",
                "skills",
                self.sleep_coding_skills,
            )
        )

    @property
    def resolved_sleep_coding_mcp_servers(self) -> list[str]:
        return self._resolve_string_list(
            self._get_agent_setting(
                "ralph",
                "mcp_servers",
                self.sleep_coding_mcp_servers,
            )
        )

    @property
    def resolved_sleep_coding_model_profile(self) -> str | None:
        return self._get_agent_setting("ralph", "model_profile", None)

    @property
    def resolved_review_workspace(self) -> Path:
        return self._resolve_workspace_path(
            self._get_agent_setting("code-review-agent", "workspace", self.review_workspace)
        )

    @property
    def resolved_review_skills(self) -> list[str]:
        return self._resolve_string_list(
            self._get_agent_setting("code-review-agent", "skills", self.review_skills)
        )

    @property
    def resolved_review_mcp_servers(self) -> list[str]:
        return self._resolve_string_list(
            self._get_agent_setting(
                "code-review-agent",
                "mcp_servers",
                self.review_mcp_servers,
            )
        )

    @property
    def resolved_review_model_profile(self) -> str | None:
        return self._get_agent_setting("code-review-agent", "model_profile", None)

    def resolve_agent_spec(self, agent_id: str) -> AgentSpec:
        defaults = self._default_agent_spec(agent_id)
        resolved_workspace = self._resolve_workspace_path(
            self._get_agent_setting(agent_id, "workspace", defaults["workspace"])
        )
        skills = self._resolve_string_list(
            self._get_agent_setting(agent_id, "skills", defaults["skills"])
        )
        mcp_servers = self._resolve_string_list(
            self._get_agent_setting(agent_id, "mcp_servers", defaults["mcp_servers"])
        )
        model_profile = self._get_agent_setting(
            agent_id,
            "model_profile",
            defaults["model_profile"],
        )
        system_instruction = str(
            self._get_agent_setting(
                agent_id,
                "system_instruction",
                defaults["system_instruction"],
            )
        ).strip()
        memory_policy = str(
            self._get_agent_setting(
                agent_id,
                "memory_policy",
                defaults["memory_policy"],
            )
        ).strip()
        execution_policy = str(
            self._get_agent_setting(
                agent_id,
                "execution_policy",
                defaults["execution_policy"],
            )
        ).strip()
        return AgentSpec(
            agent_id=agent_id,
            workspace=resolved_workspace,
            skills=skills,
            mcp_servers=mcp_servers,
            model_profile=str(model_profile).strip() if isinstance(model_profile, str) and model_profile.strip() else None,
            system_instruction=system_instruction,
            memory_policy=memory_policy or "short-memory",
            execution_policy=execution_policy or "default",
        )

    @property
    def resolved_review_skill_name(self) -> str:
        return str(
            self._get_platform_setting(
                ("review", "skill_name"),
                self.review_skill_name,
            )
        )

    @property
    def resolved_review_skill_command(self) -> str | None:
        value = self._get_platform_setting(
            ("review", "skill_command"),
            self.review_skill_command,
        )
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def resolved_mcp_config_path(self) -> Path:
        return self._resolve_project_path(self.mcp_config_path)

    @property
    def resolved_llm_default_provider(self) -> str:
        provider, _ = self.resolve_model_profile("default")
        if provider:
            return provider
        return self.llm_default_provider

    @property
    def resolved_llm_default_model(self) -> str | None:
        _, model = self.resolve_model_profile("default")
        if model:
            return model
        if self.llm_default_model:
            return self.llm_default_model
        return self.resolve_provider_default_model(self.resolved_llm_default_provider)

    @property
    def resolved_llm_request_timeout_seconds(self) -> float:
        return float(
            self._get_platform_setting(
                ("llm", "request_timeout_seconds"),
                self.llm_request_timeout_seconds,
            )
        )

    @property
    def resolved_llm_request_max_attempts(self) -> int:
        return max(
            1,
            int(
                self._get_platform_setting(
                    ("llm", "request_max_attempts"),
                    self.llm_request_max_attempts,
                )
            ),
        )

    @property
    def resolved_llm_request_retry_base_delay_seconds(self) -> float:
        return max(
            0.0,
            float(
                self._get_platform_setting(
                    ("llm", "request_retry_base_delay_seconds"),
                    self.llm_request_retry_base_delay_seconds,
                )
            ),
        )

    @property
    def resolved_openai_api_key(self) -> str | None:
        return self._get_provider_setting("openai", "api_key", self.openai_api_key)

    @property
    def resolved_openai_api_base(self) -> str:
        return str(
            self._get_provider_setting("openai", "api_base", self.openai_api_base)
        ).strip()

    @property
    def resolved_minimax_api_key(self) -> str | None:
        return self._get_provider_setting("minimax", "api_key", self.minimax_api_key)

    @property
    def resolved_minimax_api_base(self) -> str:
        return str(
            self._get_provider_setting("minimax", "api_base", self.minimax_api_base)
        ).strip()

    @property
    def resolved_openai_model(self) -> str:
        return str(
            self._get_provider_model("openai", self.openai_model)
        )

    @property
    def resolved_minimax_model(self) -> str:
        return str(
            self._get_provider_model("minimax", self.minimax_model)
        )

    def resolve_provider_protocol(self, provider: str | None) -> str:
        provider_id = self._resolve_provider_id(provider)
        provider_config = self._get_provider_config(provider_id)
        protocol = self._coerce_provider_string(
            self._get_provider_value(
                provider_config,
                "protocol",
            )
        )
        if protocol:
            return protocol
        npm_package = self._coerce_provider_string(
            self._get_provider_value(provider_config, "npm")
        )
        if npm_package and "openai" in npm_package:
            return "openai"
        if provider_config is not None:
            api_base = self._coerce_provider_string(
                self._get_provider_value(
                    provider_config,
                    "api_base",
                )
            )
            if api_base:
                return "openai"
        return provider_id

    def resolve_provider_api_key(self, provider: str | None) -> str | None:
        provider_id = self._resolve_provider_id(provider)
        provider_config = self._get_provider_config(provider_id)
        return self._coerce_provider_string(
            self._get_provider_value(
                provider_config,
                "api_key",
            )
        )

    def resolve_provider_api_base(self, provider: str | None) -> str | None:
        provider_id = self._resolve_provider_id(provider)
        provider_config = self._get_provider_config(provider_id)
        return self._coerce_provider_string(
            self._get_provider_value(
                provider_config,
                "api_base",
            )
        )

    def resolve_provider_default_model(self, provider: str | None) -> str | None:
        provider_id = self._resolve_provider_id(provider)
        provider_config = self._get_provider_config(provider_id)
        model = self._coerce_provider_string(
            self._get_provider_value(
                provider_config,
                "default_model",
            )
        )
        if model:
            return model
        return None

    def resolve_provider_pricing_provider(self, provider: str | None) -> str:
        provider_id = self._resolve_provider_id(provider)
        provider_config = self._get_provider_config(provider_id)
        value = self._coerce_provider_string(
            self._get_provider_value(
                provider_config,
                "pricing_provider",
            )
        )
        if value:
            return value
        protocol = self.resolve_provider_protocol(provider_id)
        return protocol if protocol == "openai" else provider_id

    @property
    def resolved_sleep_coding_worker_poll_interval_seconds(self) -> int:
        return int(
            self._get_platform_setting(
                ("sleep_coding", "worker", "poll_interval_seconds"),
                self.sleep_coding_worker_poll_interval_seconds,
            )
        )

    @property
    def resolved_sleep_coding_worker_lease_seconds(self) -> int:
        return int(
            self._get_platform_setting(
                ("sleep_coding", "worker", "lease_seconds"),
                self.sleep_coding_worker_lease_seconds,
            )
        )

    @property
    def resolved_sleep_coding_worker_heartbeat_timeout_seconds(self) -> int:
        return int(
            self._get_platform_setting(
                ("sleep_coding", "worker", "heartbeat_timeout_seconds"),
                self.sleep_coding_worker_heartbeat_timeout_seconds,
            )
        )

    @property
    def resolved_sleep_coding_worker_max_retries(self) -> int:
        return int(
            self._get_platform_setting(
                ("sleep_coding", "worker", "max_retries"),
                self.sleep_coding_worker_max_retries,
            )
        )

    @property
    def resolved_sleep_coding_worker_retry_backoff_seconds(self) -> int:
        return int(
            self._get_platform_setting(
                ("sleep_coding", "worker", "retry_backoff_seconds"),
                self.sleep_coding_worker_retry_backoff_seconds,
            )
        )

    @property
    def resolved_sleep_coding_worker_auto_approve_plan(self) -> bool:
        return bool(
            self._get_platform_setting(
                ("sleep_coding", "worker", "auto_approve_plan"),
                self.sleep_coding_worker_auto_approve_plan,
            )
        )

    @property
    def resolved_sleep_coding_scheduler_enabled(self) -> bool:
        return bool(
            self._get_platform_setting(
                ("sleep_coding", "worker", "scheduler_enabled"),
                self.sleep_coding_scheduler_enabled,
            )
        )

    @property
    def resolved_sleep_coding_enable_git_commit(self) -> bool:
        return bool(
            self._get_platform_setting(
                ("sleep_coding", "git", "enable_commit"),
                self.sleep_coding_enable_git_commit,
            )
        )

    @property
    def resolved_sleep_coding_enable_git_push(self) -> bool:
        return bool(
            self._get_platform_setting(
                ("sleep_coding", "git", "enable_push"),
                self.sleep_coding_enable_git_push,
            )
        )

    @property
    def resolved_git_remote_name(self) -> str:
        return str(
            self._get_platform_setting(
                ("sleep_coding", "git", "remote_name"),
                self.git_remote_name,
            )
        )

    @property
    def resolved_sleep_coding_validation_command(self) -> str:
        return str(
            self._get_platform_setting(
                ("sleep_coding", "validation", "command"),
                self.sleep_coding_validation_command,
            )
        ).strip()

    @property
    def resolved_sleep_coding_validation_timeout_seconds(self) -> float:
        value = self._get_platform_setting(
            ("sleep_coding", "validation", "timeout_seconds"),
            self.sleep_coding_validation_timeout_seconds,
        )
        return max(float(value), 1.0)

    @property
    def resolved_review_max_repair_rounds(self) -> int:
        return int(
            self._get_platform_setting(
                ("review", "max_repair_rounds"),
                self.review_max_repair_rounds,
            )
        )

    @property
    def has_runtime_llm_credentials(self) -> bool:
        if self.resolve_provider_api_key(self.resolved_llm_default_provider):
            return True
        providers = self.models_config.get("providers", {})
        if isinstance(providers, dict):
            for provider_name in providers:
                if self.resolve_provider_api_key(str(provider_name)):
                    return True
        return bool(self.resolved_openai_api_key or self.resolved_minimax_api_key)

    def resolve_model_profile(
        self,
        profile_name: str | None,
    ) -> tuple[str | None, str | None]:
        if not profile_name:
            return None, None
        profiles = self.models_config.get("profiles", {})
        if not isinstance(profiles, dict):
            return None, None
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            return None, None
        provider = profile.get("provider")
        model = profile.get("model")
        provider_text = str(provider).strip() if isinstance(provider, str) and provider.strip() else None
        model_text = str(model).strip() if isinstance(model, str) and model.strip() else None
        if provider_text is None and model_text and "/" in model_text:
            provider_candidate, _, model_candidate = model_text.partition("/")
            provider_candidate = provider_candidate.strip()
            model_candidate = model_candidate.strip()
            if provider_candidate and model_candidate:
                return provider_candidate, model_candidate
        return (
            provider_text,
            model_text,
        )

    def _load_json_config(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"JSON config must be an object: {path}")
        return loaded

    def _get_agent_setting(
        self,
        agent_id: str,
        key: str,
        default: object,
    ) -> object:
        agents = self.agents_config.get("agents", {})
        if isinstance(agents, dict):
            agent = agents.get(agent_id)
            if isinstance(agent, dict) and key in agent:
                return agent[key]
        return default

    def _default_agent_spec(self, agent_id: str) -> dict[str, Any]:
        defaults: dict[str, dict[str, Any]] = {
            "main-agent": {
                "workspace": self.main_agent_workspace,
                "skills": self.main_agent_skills,
                "mcp_servers": self.main_agent_mcp_servers,
                "model_profile": "default",
                "system_instruction": (
                    "Convert user requests into executable GitHub issues that Ralph can execute "
                    "through the sleep-coding workflow."
                ),
                "memory_policy": "short-memory",
                "execution_policy": "issue-intake",
            },
            "ralph": {
                "workspace": self.sleep_coding_workspace,
                "skills": self.sleep_coding_skills,
                "mcp_servers": self.sleep_coding_mcp_servers,
                "model_profile": "coding",
                "system_instruction": (
                    "Plan and execute software tasks with concrete code changes, tests, and GitHub workflow hygiene."
                ),
                "memory_policy": "short-memory",
                "execution_policy": "sleep-coding",
            },
            "code-review-agent": {
                "workspace": self.review_workspace,
                "skills": self.review_skills,
                "mcp_servers": self.review_mcp_servers,
                "model_profile": "review",
                "system_instruction": (
                    "Review code changes and return structured findings that automation can route."
                ),
                "memory_policy": "short-memory",
                "execution_policy": "review",
            },
        }
        if agent_id not in defaults:
            raise ValueError(f"Unknown agent spec: {agent_id}")
        return defaults[agent_id]

    def _get_platform_setting(
        self,
        path: tuple[str, ...],
        default: object,
    ) -> object:
        current: object = self.platform_config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    def _resolve_string_list(self, raw: object) -> list[str]:
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str):
            return [item.strip() for item in raw.split(",") if item.strip()]
        return []

    def _resolve_project_path(self, raw: str | Path) -> Path:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else self.project_root / path

    def _resolve_workspace_path(self, raw: object) -> Path:
        return self._resolve_project_path(str(raw))

    def _resolve_platform_bool(self, path: tuple[str, ...], default: bool) -> bool:
        return bool(self._get_platform_setting(path, default))

    def _get_default_model_profile(self) -> dict[str, object]:
        profiles = self.models_config.get("profiles", {})
        if not isinstance(profiles, dict):
            return {}
        profile = profiles.get("default")
        return profile if isinstance(profile, dict) else {}

    def _get_provider_model(self, provider: str, fallback: str) -> str:
        model = self.resolve_provider_default_model(provider)
        if model:
            return model
        fallback_text = fallback.strip()
        if fallback_text:
            return fallback_text
        protocol = self.resolve_provider_protocol(provider)
        if protocol == "openai":
            return self.openai_model
        return fallback

    def _get_provider_setting(
        self,
        provider: str,
        key: str,
        fallback: str | None,
    ) -> str | None:
        provider_config = self._get_provider_config(provider)
        if provider_config is not None:
            value = self._get_provider_value(provider_config, key)
            if value is None:
                return fallback.strip() or None if isinstance(fallback, str) else fallback
            text = str(value).strip()
            return text or None
        return fallback.strip() or None if isinstance(fallback, str) else fallback

    def _get_provider_config(self, provider: str) -> dict[str, object] | None:
        provider = provider.strip()
        builtin = self._get_builtin_provider_config(provider)
        providers = self.models_config.get("providers", {})
        if isinstance(providers, dict):
            provider_config = providers.get(provider)
            if isinstance(provider_config, dict):
                if builtin is None:
                    return dict(provider_config)
                merged = dict(builtin)
                merged.update(provider_config)
                return merged
        return builtin

    def _get_provider_value(
        self,
        provider_config: dict[str, object] | None,
        *paths: str,
    ) -> object:
        if provider_config is None:
            return None
        for path in paths:
            current: object = provider_config
            for key in path.split("."):
                if not isinstance(current, dict) or key not in current:
                    current = None
                    break
                current = current[key]
            if current is not None:
                return current
        return None

    def _coerce_provider_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _resolve_provider_id(self, provider: str | None) -> str:
        provider_id = (provider or "").strip()
        if provider_id:
            return provider_id
        return self.resolved_llm_default_provider

    def _get_builtin_provider_config(self, provider: str) -> dict[str, object] | None:
        if provider == "openai":
            return {
                "protocol": "openai",
                "api_key": self.openai_api_key,
                "api_base": self.openai_api_base,
                "default_model": self.openai_model,
                "pricing_provider": "openai",
            }
        if provider == "minimax":
            return {
                "protocol": "openai",
                "api_key": self.minimax_api_key,
                "api_base": self.minimax_api_base,
                "default_model": self.minimax_model,
                "pricing_provider": "minimax",
            }
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
