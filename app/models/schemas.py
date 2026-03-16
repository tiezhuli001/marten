from typing import Any, Literal

from pydantic import BaseModel, Field

IntentType = Literal["general", "stats_query", "sleep_coding"]
ReviewStatus = Literal[
    "pending",
    "running",
    "completed",
    "approved",
    "changes_requested",
    "cancelled",
    "failed",
]
ReviewDecision = Literal["approve_review", "request_changes", "cancel_review"]
TaskStatus = Literal[
    "created",
    "planning",
    "awaiting_confirmation",
    "coding",
    "validating",
    "pr_opened",
    "in_review",
    "changes_requested",
    "approved",
    "merged",
    "failed",
    "cancelled",
]
TaskAction = Literal[
    "approve_plan",
    "reject_plan",
    "approve_pr",
    "request_changes",
    "cancel_task",
]
ValidationStatus = Literal["pending", "passed", "failed", "skipped"]
ExecutionStatus = Literal["pending", "prepared", "skipped", "completed", "failed"]
ReviewSourceType = Literal["github_pr", "gitlab_mr", "local_code", "sleep_coding_task"]


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    model_name: str | None = None
    provider: str | None = None
    cost_usd: float = Field(default=0.0, ge=0.0)
    step_name: str | None = None


class TokenUsageBreakdown(BaseModel):
    label: str
    request_count: int = Field(default=0, ge=0)
    workflow_run_count: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)


class TokenWindowSummary(BaseModel):
    window: Literal["7d", "30d"]
    start_date: str
    end_date: str
    request_count: int = Field(default=0, ge=0)
    workflow_run_count: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    by_intent: list[TokenUsageBreakdown] = Field(default_factory=list)
    by_step_name: list[TokenUsageBreakdown] = Field(default_factory=list)
    top_requests: list[TokenUsageBreakdown] = Field(default_factory=list)


class DailyTokenSummary(BaseModel):
    summary_date: str
    request_count: int = Field(default=0, ge=0)
    workflow_run_count: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    top_intent: str | None = None
    top_step_name: str | None = None
    summary_text: str = ""


class TokenReportResponse(BaseModel):
    summary_text: str = ""
    window_summary: TokenWindowSummary | None = None
    daily_summary: DailyTokenSummary | None = None


class GatewayMessageRequest(BaseModel):
    user_id: str
    content: str
    source: str = "manual"


class GatewayMessageResponse(BaseModel):
    request_id: str
    intent: IntentType
    message: str
    token_usage: TokenUsage


class SleepCodingIssue(BaseModel):
    issue_number: int = Field(ge=1)
    title: str
    body: str
    state: str = "open"
    html_url: str | None = None
    labels: list[str] = Field(default_factory=list)
    is_dry_run: bool = False


class SleepCodingPlan(BaseModel):
    summary: str
    scope: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    status: ValidationStatus = "pending"
    command: str = "python -m unittest discover -s tests"
    exit_code: int | None = None
    output: str = ""


class SleepCodingPullRequest(BaseModel):
    title: str
    body: str
    html_url: str | None = None
    pr_number: int | None = None
    state: str = "open"
    labels: list[str] = Field(default_factory=list)
    is_dry_run: bool = False


class GitExecutionResult(BaseModel):
    status: ExecutionStatus = "pending"
    worktree_path: str | None = None
    artifact_path: str | None = None
    commit_sha: str | None = None
    push_remote: str | None = None
    output: str = ""
    is_dry_run: bool = True


class SleepCodingTaskEvent(BaseModel):
    id: int
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SleepCodingTaskRequest(BaseModel):
    issue_number: int = Field(ge=1)
    repo: str | None = None
    base_branch: str = "main"
    head_branch: str | None = None
    issue_title: str | None = None
    issue_body: str | None = None
    request_id: str | None = None


class SleepCodingTaskActionRequest(BaseModel):
    action: TaskAction


class SleepCodingTask(BaseModel):
    task_id: str
    issue_number: int
    repo: str
    base_branch: str
    head_branch: str
    status: TaskStatus
    issue: SleepCodingIssue
    plan: SleepCodingPlan | None = None
    git_execution: GitExecutionResult = Field(default_factory=GitExecutionResult)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    pull_request: SleepCodingPullRequest | None = None
    events: list[SleepCodingTaskEvent] = Field(default_factory=list)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    last_error: str | None = None
    kickoff_request_id: str | None = None
    created_at: str
    updated_at: str


class ReviewSource(BaseModel):
    source_type: ReviewSourceType
    repo: str | None = None
    pr_number: int | None = None
    mr_number: int | None = None
    project_path: str | None = None
    url: str | None = None
    local_path: str | None = None
    base_branch: str | None = None
    head_branch: str | None = None
    task_id: str | None = None


class ReviewRunRequest(BaseModel):
    source: ReviewSource


class ReviewActionRequest(BaseModel):
    action: ReviewDecision


class ReviewRun(BaseModel):
    review_id: str
    source: ReviewSource
    status: ReviewStatus
    artifact_path: str | None = None
    comment_url: str | None = None
    summary: str = ""
    content: str = ""
    run_mode: Literal["dry_run", "real_run"] = "dry_run"
    task_id: str | None = None
    created_at: str
    updated_at: str
    reviewed_at: str | None = None
