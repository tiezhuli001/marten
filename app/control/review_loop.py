from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ReviewLoopAction = Literal[
    "rerun_coding",
    "run_review",
    "request_changes",
    "approve_review",
    "handoff",
    "deliver",
    "stop",
]


@dataclass(frozen=True)
class ReviewLoopDecision:
    action: ReviewLoopAction
    blocking_reviews: int = 0


def decide_review_loop_step(
    *,
    task_status: str,
    review_blocking: bool | None = None,
    blocking_reviews: int = 0,
    max_repair_rounds: int,
) -> ReviewLoopDecision:
    if task_status == "changes_requested":
        if blocking_reviews >= max_repair_rounds:
            return ReviewLoopDecision("stop", blocking_reviews=blocking_reviews)
        return ReviewLoopDecision("rerun_coding", blocking_reviews=blocking_reviews)
    if task_status == "in_review":
        if review_blocking is None:
            return ReviewLoopDecision("run_review", blocking_reviews=blocking_reviews)
        if review_blocking and blocking_reviews >= max_repair_rounds:
            return ReviewLoopDecision("handoff", blocking_reviews=blocking_reviews)
        if review_blocking:
            return ReviewLoopDecision("request_changes", blocking_reviews=blocking_reviews)
        return ReviewLoopDecision("approve_review", blocking_reviews=blocking_reviews)
    if task_status in {"approved", "failed", "cancelled"}:
        return ReviewLoopDecision("deliver", blocking_reviews=blocking_reviews)
    return ReviewLoopDecision("stop", blocking_reviews=blocking_reviews)
