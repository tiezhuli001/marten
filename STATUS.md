## Goal

把新的 agent runtime contract 下沉到真实运行时输出，而不是只停留在 `AGENTS.md`：

- `main-agent` 真实区分 `chat` 与 `coding_handoff`
- `ralph` 输出结构化 handoff / coding artifact / review handoff
- `code-review-agent` 输出稳定的 machine / human review payload
- review loop 在 3 轮 blocking 后进入 `needs_attention`
- final delivery 只在 review 通过后触发
- provider 切换不影响上层 retrieval contract

## Baseline

- `docs/architecture/agent-first-implementation-principles.md`
- `docs/architecture/agent-runtime-contracts.md`
- `docs/architecture/agent-system-overview.md`
- `docs/architecture/rag-provider-surface.md`
- `docs/handoffs/README.md`
- 本地 `docs/internal/handoffs/` 下与当前任务相关的 latest handoff（若存在）

## Done Criteria

- runtime 输出与 agent contract 文档对齐
- 新增主链回归测试覆盖上述关键行为
- 相关单元测试通过
- 完成一轮目标偏移检查
- `STATUS.md` 与 handoff 文档同步

## Done

- 当前工作已从 `main` 切到工作分支 `codex/docs-internal-handoff-boundaries`，避免继续在主分支上修改
- README 入口已重构为更适合 GitHub 开源首页的英文主页面，并新增中文镜像 `README_CN.md`
- 主 README 顶部已加入 `中文文档`、核心架构文档入口、badge 与主链 workflow 图
- README 与 `README_CN.md` 中的 Mermaid workflow 已完成真实 CLI 渲染校验，确保 GitHub 可渲染
- 明确 docs 目录边界：
- `docs/handoffs/` 只保留规则与模板
- 具体 handoff 统一迁回本地 `docs/internal/handoffs/`
- `docs/internal/` 只用于本地开发，不提交远程仓库
- 删除无长期价值的历史文档：
- `docs/archive/plans/*.md`
- `docs/superpowers/plans/2026-03-22-framework-implementation.md`
- 本地过期 `docs/internal/session-handoff.md`
- 本地过期 `docs/internal/rag-stack-baseline.md`
- `MainAgentIntakeResponse` 扩展为显式 `mode` / `chat_response` / `handoff`，并新增 `needs_attention` task status
- 新增 `docs/architecture/agent-first-implementation-principles.md`，明确 2026 年阶段的 `agent-first` / `LLM + MCP + skill first` 实现边界
- 在 `docs/architecture/agent-system-overview.md`、`docs/architecture/agent-runtime-contracts.md`、`docs/handoffs/README.md` 中补充该原则的引用与落地要求
- 把 runtime payload 从自由 dict 收口到显式 schema：
- `MainAgentCodingHandoff`
- `RalphCodingArtifact`
- `RalphReviewHandoff`
- `ReviewMachineOutput`
- `ReviewHumanOutput`
- `main-agent` intake 运行时现已：
- 对非编码请求返回 `chat` mode，不创建 issue / control task / 通知
- 对编码请求返回 `coding_handoff`，并把结构化 handoff 写入 control task payload
- 对 provider 返回非 JSON 的情况，保留真实 LLM token usage，同时回退到启发式 handoff
- 对 coding handoff 使用 `MainAgentCodingHandoff` schema，再写入 control task payload
- `gateway` 已消费 `main-agent` 的 `chat` / `coding_handoff` 分流，不再无条件拼接 issue URL
- `ralph` 运行时现已输出：
- `coding_artifact` 到 control task payload
- `review_handoff` 到 control task payload，并把下一责任 agent 固定为 `code-review-agent`
- `coding_draft_generated` 事件中新增结构化 `artifact`
- `code-review-agent` control task payload 现已稳定包含：
- `machine_output`：`ReviewMachineOutput`
- `human_output`：`ReviewHumanOutput`
- `ralph` 的 `coding_artifact` / `review_handoff` 现已通过 `RalphCodingArtifact` / `RalphReviewHandoff` schema 写入 payload 与事件
- `automation` review loop 现已：
- 对已 `approved` 但未 review 的任务，先补 review gate，再决定 delivery
- 在 3 轮 blocking review 后把 Ralph domain task 与 control task 都推进到 `needs_attention`
- 仅在 review 已批准后触发 final delivery
- 保持 `RAGFacade` / retrieval contract 不变；`Qdrant` / `Milvus` provider 切换相关回归仍然通过
- 同步更新了 `tests/test_main_agent.py`、`tests/test_gateway.py`、`tests/test_sleep_coding.py`、`tests/test_review.py`、`tests/test_automation.py`
- 已处理最新一轮 code review follow-up：
- 修复 `app/agents/ralph/application.py` 中 `resume_task()` 的死分支，删除 `validating` 路径下永远不会命中的 `pending_usage` 后处理
- 统一 `app/agents/main_agent/application.py` 的 scope clarification 文案为英文，避免中英混杂
- 为 review gate / review return payload 补充直接测试，覆盖显式 `validation_gap` 放行与 `repair_strategy` / `review_round` 返回负载
- 明确保留以下实现，不做误修：
- `app/agents/ralph/workflow.py` 中 `json` import 仍被 `_resolve_commit_message()` 使用
- `app/agents/ralph/progress.py` 中 `record_validation_failure()` 的 `validation` / `git_execution` 参数仍会整体写入 task payload，不是只取 `validation.status`
- `app/agents/main_agent/application.py` 中 `broad_area_markers` 继续保持为小型启发式常量，不扩展成配置项，避免为单点 intake heuristic 引入额外配置面

## In Progress

- 无

## Next

- 如需继续 README 打磨，可补实际截图、演示 GIF 或架构图资源，但当前纯 Markdown 首页已经可作为稳定开源入口
- 如需继续深化，可把 `main-agent` chat mode 的 reply contract 接入更明确的 UI / channel 展示层
- 如需继续深化，可补 end-to-end API 层回归，锁住 gateway -> main-agent -> ralph -> review -> delivery 全链 JSON 输出
- 当前 review-fix 已收口；若继续推进，应优先补更高层的全链 API / live-chain 回归，而不是继续扩张局部 heuristic 配置

## Blockers

- 无

## Verification

- `python - <<'PY' ...`（校验 `README.md` 与 `README_CN.md` 的相对 Markdown 链接） -> PASS (`OK`)
- `python - <<'PY' ...`（提取 `README.md` / `README_CN.md` 中的 Mermaid 图并用 `@mermaid-js/mermaid-cli` 渲染） -> PASS (`README.md: block 1 OK`, `README_CN.md: block 1 OK`)
- `python -m unittest discover -s tests -v` -> PASS (`Ran 157 tests in 145.114s`)
- `python -m unittest tests.test_main_agent.MainAgentServiceTests.test_intake_returns_chat_mode_for_non_coding_question tests.test_automation.AutomationServiceTests.test_auto_review_stops_after_three_blocking_rounds_and_hands_off tests.test_automation.AutomationServiceTests.test_approved_task_without_review_does_not_skip_review_gate tests.test_review.ReviewServiceTests.test_trigger_for_task_records_review_and_comment tests.test_sleep_coding.SleepCodingServiceTests.test_sleep_coding_emits_structured_handoff_and_execution_artifacts -v` -> PASS
- `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_review tests.test_automation tests.test_rag_capability tests.test_runtime_components tests.test_framework_public_surface -v` -> PASS (`Ran 97 tests in 14.798s`)
- `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_review tests.test_automation tests.test_rag_capability tests.test_runtime_components tests.test_framework_public_surface -v` -> PASS (`Ran 97 tests in 16.265s`)
- `python -m unittest tests.test_review tests.test_main_agent tests.test_sleep_coding -v` -> PASS (`Ran 60 tests in 8.109s`)
- `rg -n "chat mode|coding handoff|needs_attention|review_handoff|machine_output|human_output|retrieval contract|provider" docs/architecture docs/evolution -g '*.md'` -> PASS（当前实现关注点仍与 runtime contract / provider surface 文档一致）
- `rg -n "agent-first|LLM \\+ MCP \\+ skill first|实现边界|流程编排|agent runtime / contract" docs/architecture docs/handoffs -g '*.md'` -> PASS（原则文档已接入 architecture / handoff 文档链路）

## Goal Drift Check

- 无明显偏移
- `main-agent` 没有把普通问答继续强行送入 coding path，新增了真实 chat mode 输出
- `ralph` / `code-review-agent` 的结构化 artifact 已落到运行时 payload，不再只存在于 agent 描述文档
- review loop 的 `needs_attention` 与 final delivery gate 都按架构文档要求落到了自动化控制层
- retrieval/provider 相关测试仍通过，说明这轮 agent runtime 改动没有破坏统一 retrieval contract
- 本轮 follow-up 仅清理死分支、补 gate 测试、统一 intake 文案，没有把主链控制逻辑重新搬回硬编码，也没有引入额外兜底分叉
