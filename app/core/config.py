from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "youmeng-gateway"
    app_port: int = 8000
    app_data_dir: str = "data"
    langsmith_api_key: str | None = None
    langsmith_project: str = "youmeng-gateway"
    langsmith_tracing: bool = False
    openai_api_key: str | None = None
    database_url: str = "sqlite:///data/youmeng_gateway.db"
    github_token: str | None = None
    github_api_base: str = "https://api.github.com"
    github_repository: str = "tiezhuli001/youmeng-gateway"
    channel_provider: str = "feishu"
    channel_webhook_url: str | None = None
    sleep_coding_labels: str = "agent:ralph,workflow:sleep-coding"
    sleep_coding_worktree_root: str = ".worktrees"
    sleep_coding_enable_git_commit: bool = False
    sleep_coding_enable_git_push: bool = False
    git_remote_name: str = "origin"
    review_runs_dir: str = "docs/review-runs"
    review_skill_name: str = "code-review"
    review_skill_command: str | None = None
    gitlab_api_base: str = "https://gitlab.com/api/v4"
    gitlab_token: str | None = None

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
        data_dir = Path(self.app_data_dir).expanduser()
        return data_dir if data_dir.is_absolute() else self.project_root / data_dir

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
        return [
            item.strip()
            for item in self.sleep_coding_labels.split(",")
            if item.strip()
        ]

    @property
    def resolved_sleep_coding_worktree_root(self) -> Path:
        root = Path(self.sleep_coding_worktree_root).expanduser()
        return root if root.is_absolute() else self.project_root / root

    @property
    def resolved_review_runs_dir(self) -> Path:
        review_dir = Path(self.review_runs_dir).expanduser()
        return review_dir if review_dir.is_absolute() else self.project_root / review_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
