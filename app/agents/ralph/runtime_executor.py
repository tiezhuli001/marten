from __future__ import annotations

from app.models.schemas import SleepCodingExecutionDraft, SleepCodingIssue, SleepCodingPlan, TokenUsage
from app.runtime.agent_runtime import AgentDescriptor, AgentRuntime
from app.runtime.structured_output import parse_structured_object


class RalphRuntimeExecutor:
    def __init__(
        self,
        *,
        agent_runtime: AgentRuntime,
        agent_descriptor: AgentDescriptor,
    ) -> None:
        self.agent_runtime = agent_runtime
        self.agent_descriptor = agent_descriptor

    def generate_execution_draft(
        self,
        *,
        prompt: str,
        issue: SleepCodingIssue,
        plan: SleepCodingPlan,
        head_branch: str,
    ) -> tuple[SleepCodingExecutionDraft, TokenUsage]:
        output_contract = self._execution_output_contract()
        response = self.agent_runtime.generate_structured_output(
            self.agent_descriptor,
            user_prompt=prompt,
            workflow="sleep_coding",
            output_contract=output_contract,
        )
        try:
            draft = self._parse_execution_output(response.output_text)
        except Exception as first_error:
            repair_response = self.agent_runtime.generate_structured_output(
                self.agent_descriptor,
                user_prompt=(
                    f"{prompt}\n\n"
                    "Your previous response was invalid because it did not return strict JSON for the required schema. "
                    "Do not return shell commands, CLI flags, markdown fences, explanations, or prose. "
                    "Return only one JSON object that matches this exact shape:\n"
                    "{\n"
                    '  "artifact_markdown": "## Summary\\n...",\n'
                    '  "commit_message": "feat: concise message",\n'
                    '  "file_changes": [\n'
                    '    {"path": "relative/path.py", "content": "file contents", "description": "why this file changed"}\n'
                    "  ]\n"
                    "}\n"
                    "If you mention commands or arguments like `--repo`, your response is invalid."
                ),
                workflow="sleep_coding",
                output_contract=output_contract,
            )
            try:
                draft = self._parse_execution_output(repair_response.output_text)
            except Exception as second_error:
                final_response = self.agent_runtime.generate_structured_output(
                    self.agent_descriptor,
                    user_prompt=(
                        "Return only strict JSON. "
                        "No commands. No arguments. No markdown fences. No explanation. "
                        "Use keys `artifact_markdown`, `commit_message`, and `file_changes` only."
                    ),
                    workflow="sleep_coding",
                    output_contract=output_contract,
                )
                try:
                    draft = self._parse_execution_output(final_response.output_text)
                except Exception as third_error:
                    raise RuntimeError(
                        "Builtin Ralph runtime returned invalid structured execution output: "
                        f"{third_error}"
                    ) from third_error
                return draft, final_response.usage.model_copy(update={"step_name": "sleep_coding_execution"})
            return draft, repair_response.usage.model_copy(update={"step_name": "sleep_coding_execution"})
        return draft, response.usage.model_copy(update={"step_name": "sleep_coding_execution"})

    def _parse_execution_output(self, output_text: str) -> SleepCodingExecutionDraft:
        return SleepCodingExecutionDraft.model_validate(parse_structured_object(output_text))

    def _execution_output_contract(self) -> str:
        return (
            "Return strict JSON with keys `artifact_markdown`, `commit_message`, and `file_changes`. "
            "`artifact_markdown` must be markdown for `.sleep_coding/issue-<n>.md`. "
            "`commit_message` must be concise and specific. "
            "`file_changes` must be an array of objects with keys `path`, `content`, and `description`. "
            "Do not return shell commands, CLI flags, prose, markdown fences, or tool invocation syntax. "
            "The draft must reflect the real coding work Ralph would perform in the local worktree for this issue and plan."
        )
