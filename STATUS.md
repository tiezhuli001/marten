## Goal

把新的 agent runtime contract 下沉到真实运行时输出，而不是只停留在 `AGENTS.md`：

- `main-agent` 真实区分 `chat` 与 `coding_handoff`
- `ralph` 输出结构化 handoff / coding artifact / review handoff
- `code-review-agent` 输出稳定的 machine / human review payload
- review loop 在 3 轮 blocking 后进入 `needs_attention`
- final delivery 只在 review 通过后触发
- provider 切换不影响上层 retrieval contract

## Baseline

- `docs/architecture/agent-runtime-contracts.md`
- `docs/architecture/agent-system-overview.md`
- `docs/architecture/rag-provider-surface.md`
- `docs/handoffs/2026-03-23-rag-provider-runtime-handoff.md`

## Done Criteria

- runtime 输出与 agent contract 文档对齐
- 新增主链回归测试覆盖上述关键行为
- 相关单元测试通过
- 完成一轮目标偏移检查
- `STATUS.md` 与 handoff 文档同步

## Done

- `MainAgentIntakeResponse` 扩展为显式 `mode` / `chat_response` / `handoff`，并新增 `needs_attention` task status
- `main-agent` intake 运行时现已：
- 对非编码请求返回 `chat` mode，不创建 issue / control task / 通知
- 对编码请求返回 `coding_handoff`，并把结构化 handoff 写入 control task payload
- 对 provider 返回非 JSON 的情况，保留真实 LLM token usage，同时回退到启发式 handoff
- `gateway` 已消费 `main-agent` 的 `chat` / `coding_handoff` 分流，不再无条件拼接 issue URL
- `ralph` 运行时现已输出：
- `coding_artifact` 到 control task payload
- `review_handoff` 到 control task payload，并把下一责任 agent 固定为 `code-review-agent`
- `coding_draft_generated` 事件中新增结构化 `artifact`
- `code-review-agent` control task payload 现已稳定包含：
- `machine_output`：`blocking` / `severity_counts` / `findings` / `repair_strategy`
- `human_output`：`summary` / `review_markdown` / `comment_url`
- `automation` review loop 现已：
- 对已 `approved` 但未 review 的任务，先补 review gate，再决定 delivery
- 在 3 轮 blocking review 后把 Ralph domain task 与 control task 都推进到 `needs_attention`
- 仅在 review 已批准后触发 final delivery
- 保持 `RAGFacade` / retrieval contract 不变；`Qdrant` / `Milvus` provider 切换相关回归仍然通过
- 同步更新了 `tests/test_main_agent.py`、`tests/test_gateway.py`、`tests/test_sleep_coding.py`、`tests/test_review.py`、`tests/test_automation.py`

## In Progress

- 无

## Next

- 如需继续深化，可把 `main-agent` chat mode 的 reply contract 接入更明确的 UI / channel 展示层
- 如需继续深化，可把 `review_handoff` / `machine_output` / `human_output` 抽成显式 schema，避免 payload dict 漂移
- 如需继续深化，可补 end-to-end API 层回归，锁住 gateway -> main-agent -> ralph -> review -> delivery 全链 JSON 输出

## Blockers

- 无

## Verification

- `python -m unittest tests.test_main_agent.MainAgentServiceTests.test_intake_returns_chat_mode_for_non_coding_question tests.test_automation.AutomationServiceTests.test_auto_review_stops_after_three_blocking_rounds_and_hands_off tests.test_automation.AutomationServiceTests.test_approved_task_without_review_does_not_skip_review_gate tests.test_review.ReviewServiceTests.test_trigger_for_task_records_review_and_comment tests.test_sleep_coding.SleepCodingServiceTests.test_sleep_coding_emits_structured_handoff_and_execution_artifacts -v` -> PASS
- `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_review tests.test_automation tests.test_rag_capability tests.test_runtime_components tests.test_framework_public_surface -v` -> PASS (`Ran 97 tests in 14.798s`)
- `rg -n "chat mode|coding handoff|needs_attention|review_handoff|machine_output|human_output|retrieval contract|provider" docs/architecture docs/evolution -g '*.md'` -> PASS（当前实现关注点仍与 runtime contract / provider surface 文档一致）

## Goal Drift Check

- 无明显偏移
- `main-agent` 没有把普通问答继续强行送入 coding path，新增了真实 chat mode 输出
- `ralph` / `code-review-agent` 的结构化 artifact 已落到运行时 payload，不再只存在于 agent 描述文档
- review loop 的 `needs_attention` 与 final delivery gate 都按架构文档要求落到了自动化控制层
- retrieval/provider 相关测试仍通过，说明这轮 agent runtime 改动没有破坏统一 retrieval contract
