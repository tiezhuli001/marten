import shlex

from app.agents.code_review_agent.application import (
    ReviewService,
    ReviewSkillRunResult,
    ReviewSkillService as AgentReviewSkillService,
    which,
)
from app.models.schemas import ReviewSource


class ReviewSkillService(AgentReviewSkillService):
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


__all__ = [
    "ReviewService",
    "ReviewSkillRunResult",
    "ReviewSkillService",
    "which",
]
