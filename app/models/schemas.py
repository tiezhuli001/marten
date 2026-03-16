from typing import Any, Literal

from pydantic import BaseModel, Field

IntentType = Literal["general", "stats_query", "sleep_coding"]
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


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


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
