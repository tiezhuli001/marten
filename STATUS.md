## Goal

执行 `docs/plans/2026-03-23-agent-native-runtime-followup-hardening.md`，把当前“第一轮纠偏已完成，但旧配置/兼容壳/worktree-native runtime 尚未收口”的状态继续推进到：

- 不再保留 command-native 主链配置面
- 不再保留 command-compatible 主链实现壳
- `ralph` 真正拥有本地 worktree 编码与验证闭环
- `code-review-agent` 真正拥有基于 worktree/diff/evidence 的 review 闭环
- diagnostics / live-chain 只认 builtin runtime truth

## Current Phase

- `agent-native runtime follow-up hardening` 已完成并验收通过

## Current Target

- 保持已完成的 builtin-agent worktree-native 主链收口状态
- 维持 diagnostics / live-chain 与真实 builtin runtime truth 对齐
- 如需下一步，只处理新的用户需求，不回退 command/fallback 兼容壳

## Next Action

- 当前计划已完成，无进行中执行项
- 若继续迭代，优先关注新增需求，不再为旧 command/fallback 路径补兼容

## Completed Work

- 新增 follow-up 执行计划：
  - `/Users/litiezhu/workspace/github/marten/docs/plans/2026-03-23-agent-native-runtime-followup-hardening.md`
- 完成 Chunk 1：
  - 同步 architecture/source-of-truth 文档，明确 builtin `ralph` / builtin `code-review-agent` 是标准主链 owner
  - 明确 external command 不是默认主路径，关键失败必须显式暴露
- 完成 Chunk 2：
  - 新增 `app/runtime/context_policy.py`
  - `AgentRuntime` 改为通过显式 policy 组装 bootstrap / workspace / skills / MCP / RAG / output contract
  - RAG 支持 `runtime_only` 注入策略和按优先级截断
- 完成 Chunk 3：
  - 新增 `app/agents/ralph/runtime_executor.py`
  - `RalphDraftingService.build_execution_draft()` 默认切到 builtin runtime
  - 缺少凭据时显式报 `Builtin Ralph runtime is unavailable`
  - builtin execution 返回非法结构化输出时直接失败，不再回退到 heuristic execution success
- 完成 Chunk 4：
  - 新增 `app/agents/code_review_agent/runtime_reviewer.py`
  - `ReviewSkillService.run()` 默认切到 builtin runtime
  - review runtime 失败直接抛错
  - 非法 structured review output 直接失败，不再降级成 permissive non-blocking review
- 完成 Chunk 5 配套回归收口：
  - worker / automation / MVP 夹具全部改成显式注入 fake builtin runtimes，和新的主链前提保持一致
  - 主链回归确认 gateway -> main-agent -> ralph -> code-review-agent -> delivery 仍可通过
- 完成 Chunk 6 live-chain / runtime hardening 收口：
  - `app/agents/ralph/runtime_executor.py`
    - Ralph builtin execution 对非法 structured output 增加强约束修复重试
  - `app/agents/code_review_agent/runtime_reviewer.py`
    - review runtime 在 strict schema 校验前，最小化规范化可判定 shape 偏差（当前仅 `repair_strategy: str -> list[str]`）
  - `app/agents/code_review_agent/context.py`
    - review context 对 `task_id` 始终注入真实 changed files / diff / validation evidence
    - 若存在 workspace snapshot，则附加本地 worktree git snapshot，而不是覆盖任务证据
  - `tests/test_review.py`
    - 新增 builtin review scalar `repair_strategy` 规范化测试
    - 新增 workspace snapshot 存在时仍保留任务证据的上下文测试
  - `tests/test_live_chain.py`
    - live-chain 已真实跑通，确认 Ralph 编码、validation、PR、review、final delivery 全链路通过

## In Progress

- 无

## Blockers

- 无

## Verification

- `git branch --show-current`
  - `codex/context-sync-20260323`
- `test -f docs/plans/2026-03-23-agent-native-runtime-followup-hardening.md`
  - PASS
- `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests tests.test_review.ReviewServiceTests -v`
  - PASS
- `python -m unittest tests.test_sleep_coding_worker tests.test_automation tests.test_mvp_e2e -v`
  - PASS
- `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
  - PASS (`Ran 150 tests in 118.537s`)
- `python -m unittest tests.test_live_chain -v`
  - PASS (`Ran 2 tests in 150.540s`)
- `rg -n "execution.command|review.skill_command|dry-run review|fallback" docs/architecture docs/plans STATUS.md docs/internal/handoffs -g '*.md'`
  - 文档已对齐为“禁止把 fallback 作为标准主路径”的语义；剩余命中是计划/原则文档里的禁止项或历史说明，不是当前实现建议
- `rg -n "execution_command|allow_llm_fallback|review_skill_command|mode.: .command" app tests docs -g '*.py' -g '*.md'`
  - app/tests 无主链残留；剩余命中仅在计划文档和断言“已删除”的测试中

## Goal Drift Check

- 无新的目标偏移
- 本轮已完成此前识别的主链偏移收口：
  - 旧配置面已关闭
  - 旧 command-compatible 壳已删除
  - diagnostics 已不再认可 command/fallback 能力面
  - Ralph / Review 已按 builtin-agent + worktree evidence 主链运行
  - live-chain 已真实执行并通过
