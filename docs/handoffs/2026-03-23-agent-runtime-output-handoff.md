# 2026-03-23 Agent Runtime Output Handoff

## Summary

本次工作把新的 agent contract 从文档层下沉到运行时输出，重点覆盖 `main-agent`、`ralph`、`code-review-agent` 与 review automation 主链。

## Scope Completed

- `main-agent`
- intake 现在区分 `chat` 与 `coding_handoff`
- `chat` mode 不创建 issue / control task / 通知
- `coding_handoff` mode 在 control task payload 中保留结构化 handoff

- `ralph`
- 生成 `coding_artifact` payload
- 在进入 review 前生成 `review_handoff`
- `coding_draft_generated` 事件带结构化 `artifact`

- `code-review-agent`
- control task payload 中新增稳定的 `machine_output` 与 `human_output`

- `automation`
- `approved` 任务不会跳过 review gate
- 连续 3 轮 blocking review 后，domain/control task 一致进入 `needs_attention`
- final delivery 仅在 review 已批准后触发

- `rag`
- 未修改 `RAGFacade` surface
- `Qdrant` / `Milvus` provider contract 回归仍通过

## Files Changed

- `app/models/schemas.py`
- `app/agents/main_agent/application.py`
- `app/control/gateway.py`
- `app/agents/ralph/application.py`
- `app/agents/ralph/workflow.py`
- `app/agents/ralph/progress.py`
- `app/agents/code_review_agent/application.py`
- `app/control/automation.py`
- `tests/test_main_agent.py`
- `tests/test_gateway.py`
- `tests/test_sleep_coding.py`
- `tests/test_review.py`
- `tests/test_automation.py`

## Verification

- `python -m unittest tests.test_main_agent.MainAgentServiceTests.test_intake_returns_chat_mode_for_non_coding_question tests.test_automation.AutomationServiceTests.test_auto_review_stops_after_three_blocking_rounds_and_hands_off tests.test_automation.AutomationServiceTests.test_approved_task_without_review_does_not_skip_review_gate tests.test_review.ReviewServiceTests.test_trigger_for_task_records_review_and_comment tests.test_sleep_coding.SleepCodingServiceTests.test_sleep_coding_emits_structured_handoff_and_execution_artifacts -v`
- `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_review tests.test_automation tests.test_rag_capability tests.test_runtime_components tests.test_framework_public_surface -v`

结果：`Ran 97 tests in 14.798s`，全部通过。

## Alignment Check

- 对齐 `docs/architecture/agent-runtime-contracts.md`
- 对齐 `docs/architecture/agent-system-overview.md`
- 保持 `docs/architecture/rag-provider-surface.md` 的统一 retrieval/provider surface

未发现目标偏移。本轮改动是把既有设计落到 runtime 输出与回归测试，而不是引入新的 agent flow。

## Suggested Next Step

- 如果下一轮继续收紧 contract，优先把 `coding_artifact` / `review_handoff` / `machine_output` / `human_output` 升级为显式 schema，并补 API 层序列化回归。
