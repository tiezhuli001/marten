from typing import Any, Literal

from pydantic import BaseModel, Field

IntentType = Literal["general", "stats_query", "sleep_coding"]
ProviderType = str
MessageRole = Literal["system", "user", "assistant"]
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
BackgroundFollowUpStatus = Literal["idle", "queued", "processing", "completed", "failed"]
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
ControlTaskType = Literal["main_agent_intake", "sleep_coding", "code_review"]
ControlSessionType = Literal["user_session", "agent_session", "run_session"]


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    message_count: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    model_name: str | None = None
    provider: str | None = None
    cost_usd: float = Field(default=0.0, ge=0.0)
    step_name: str | None = None


class LLMMessage(BaseModel):
    role: MessageRole
    content: str


class LLMRequest(BaseModel):
    messages: list[LLMMessage] = Field(default_factory=list)
    provider: ProviderType | None = None
    model: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1)


class LLMResponse(BaseModel):
    provider: ProviderType
    model: str
    output_text: str
    usage: TokenUsage
    response_id: str | None = None


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
    request_id: str | None = None
    chain_request_id: str | None = None


class GatewayMessageResponse(BaseModel):
    request_id: str
    chain_request_id: str
    intent: IntentType
    message: str
    token_usage: TokenUsage
    task_id: str | None = None
    run_session_id: str | None = None


class GitHubIssueDraft(BaseModel):
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)


class GitHubIssueResult(BaseModel):
    issue_number: int | None = Field(default=None, ge=1)
    title: str
    body: str
    html_url: str | None = None
    labels: list[str] = Field(default_factory=list)
    is_dry_run: bool = False


class WorkerDiscoveredIssue(BaseModel):
    issue_number: int = Field(ge=1)
    title: str
    body: str = ""
    state: str = "open"
    html_url: str | None = None
    labels: list[str] = Field(default_factory=list)
    is_dry_run: bool = False


class MainAgentIntakeRequest(BaseModel):
    user_id: str
    content: str
    source: str = "manual"
    repo: str | None = None
    request_id: str | None = None
    run_id: str | None = None
    persist_usage: bool = True


class MainAgentIntakeResponse(BaseModel):
    issue: GitHubIssueResult
    message: str
    token_usage: TokenUsage
    control_task_id: str | None = None


class SleepCodingWorkerPollRequest(BaseModel):
    repo: str | None = None
    worker_id: str = "sleep-coding-worker"
    auto_approve_plan: bool | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SleepCodingWorkerClaim(BaseModel):
    issue_number: int = Field(ge=1)
    repo: str
    task_id: str | None = None
    status: str
    title: str
    html_url: str | None = None
    labels: list[str] = Field(default_factory=list)
    worker_id: str | None = None
    lease_expires_at: str | None = None
    last_heartbeat_at: str | None = None
    retry_count: int = Field(default=0, ge=0)
    next_retry_at: str | None = None
    last_error: str | None = None
    created_at: str
    updated_at: str


class SleepCodingWorkerPollResponse(BaseModel):
    repo: str
    worker_id: str
    auto_approve_plan: bool
    discovered_count: int = Field(default=0, ge=0)
    claimed_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    tasks: list["SleepCodingTask"] = Field(default_factory=list)
    claims: list[SleepCodingWorkerClaim] = Field(default_factory=list)


class SleepCodingIssue(BaseModel):
    issue_number: int = Field(ge=1)
    title: str
    body: str
    state: str = "open"
    html_url: str | None = None
    labels: list[str] = Field(default_factory=list)
    creator_name: str | None = None
    creator_login: str | None = None
    is_dry_run: bool = False


class SleepCodingPlan(BaseModel):
    summary: str
    scope: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class SleepCodingFileChange(BaseModel):
    path: str
    content: str
    description: str = ""


class SleepCodingExecutionDraft(BaseModel):
    artifact_markdown: str
    commit_message: str
    file_changes: list[SleepCodingFileChange] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    severity: Literal["P0", "P1", "P2", "P3"]
    title: str
    detail: str
    file_path: str | None = None
    line: int | None = Field(default=None, ge=1)
    suggestion: str | None = None


class ReviewSkillOutput(BaseModel):
    summary: str
    findings: list[ReviewFinding] = Field(default_factory=list)
    repair_strategy: list[str] = Field(default_factory=list)
    blocking: bool | None = None
    run_mode: Literal["dry_run", "real_run"] = "dry_run"
    review_markdown: str = ""


class ValidationResult(BaseModel):
    status: ValidationStatus = "pending"
    command: str = "python scripts/run_sleep_coding_validation.py"
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
    parent_task_id: str | None = None
    notify_plan_ready: bool = True


class SleepCodingTaskActionRequest(BaseModel):
    action: TaskAction


class SleepCodingTask(BaseModel):
    task_id: str
    control_task_id: str | None = None
    parent_task_id: str | None = None
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
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    background_follow_up_status: BackgroundFollowUpStatus = "idle"
    background_follow_up_error: str | None = None
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
    control_task_id: str | None = None
    parent_task_id: str | None = None
    source: ReviewSource
    status: ReviewStatus
    artifact_path: str | None = None
    comment_url: str | None = None
    summary: str = ""
    content: str = ""
    findings: list[ReviewFinding] = Field(default_factory=list)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    is_blocking: bool = False
    run_mode: Literal["dry_run", "real_run"] = "dry_run"
    task_id: str | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    created_at: str
    updated_at: str
    reviewed_at: str | None = None


class ControlTask(BaseModel):
    task_id: str
    task_type: ControlTaskType
    agent_id: str
    status: str
    parent_task_id: str | None = None
    root_task_id: str | None = None
    user_id: str | None = None
    source: str | None = None
    repo: str | None = None
    issue_number: int | None = None
    title: str | None = None
    external_ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ControlTaskEvent(BaseModel):
    event_id: int
    task_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ControlSession(BaseModel):
    session_id: str
    session_type: ControlSessionType
    agent_id: str | None = None
    user_id: str | None = None
    source: str | None = None
    parent_session_id: str | None = None
    external_ref: str | None = None
    status: str = "active"
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


SleepCodingWorkerPollResponse.model_rebuild()
