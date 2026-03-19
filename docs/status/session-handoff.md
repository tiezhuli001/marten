# Session Handoff

> 更新时间：2026-03-19
> 用途：为下一位继续此任务的 LLM 提供压缩后的接手摘要。

## 1. 当前进展

- 当前主目标仍是收口并稳定 MVP 主链路：
  `feishu/gateway -> issue -> claim -> coding -> review -> final delivery`
- 代码侧主链路已经存在，且真实链路已验证过：
  - GitHub MCP issue/PR 真联调通过过
  - Sleep Coding worker claim / coding / PR / review / final delivery 主流程已跑通
  - LLM 失败语义已收口为：正式环境显式失败，`app_env=test` 可控回退
- 本轮新完成：
  - 新建分支：`codex/mvp-architecture-plan`
  - 已完成并归档过 4 轮架构收敛；当前生效的后续计划已切到：
    - `docs/plans/capability-gap-and-optimization-plan.md`
  - 已完成第一轮结构收敛：
    - `/gateway/message` 已退出 `WorkflowRunner` 主入口，改为 `GatewayControlPlaneService`
    - 新增 `app/control/`：
      - `gateway.py`
      - `routing.py`
      - `events.py`
    - `AutomationService` 已通过 `ControlEventBus` 调度 background follow-up
    - 已删除退出主路径的 `app/graph/*`
  - 已完成第二轮第一版结构收敛：
    - 新增 `app/agents/`
    - 新增 agent application modules：
      - `app/agents/main_agent/application.py`
      - `app/agents/ralph/application.py`
      - `app/agents/code_review_agent/application.py`
    - control plane / API / automation / worker 的主路径 import 已切到 `app/agents/*`
    - `app/services/main_agent.py`
    - `app/services/sleep_coding.py`
    - `app/services/review.py`
      现已降为兼容 facade，避免一次性大迁移
  - 已完成第三轮第一版结构收敛：
    - 新增 `app/control/context.py`
    - `SessionRegistryService` 已补：
      - `find_by_external_ref`
      - `update_session_payload`
      - `list_session_chain`
    - `control_sessions.payload` 已开始承载 `short_memory_summary`
    - main-agent / ralph / code-review-agent 已开始通过 `ContextAssemblyService` 组装上下文与写入 short memory
  - 已完成第四轮第一版结构收敛：
    - 新增 `app/channel/`
      - `notifications.py`
      - `feishu.py`
    - 新增 `app/infra/`
      - `background_jobs.py`
      - `scheduler.py`
      - `diagnostics.py`
      - `git_workspace.py`
    - `app/main.py`、`app/api/routes.py`、`app/services/automation.py`、agent 主路径 imports 已切到 `channel/infra`
    - `app/services/channel.py / feishu.py / background_jobs.py / scheduler.py / diagnostics.py / git_workspace.py`
      现已降为兼容 facade
    - `app/channel/__init__.py / app/control/__init__.py / app/infra/__init__.py`
      已改为最小入口，避免 eager import 引起循环依赖
  - 测试已回归通过：
    - `python -m unittest discover -s tests -v`
    - 当前结果：`110 tests OK`
  - 新增回测结论：
    - `IntegrationDiagnosticsService` 真实配置检查通过：
      - `github_mcp=ok`
      - `review_skill=runtime_llm`
      - `feishu=inbound/outbound ok`
    - 安全近真实全链路模拟已跑通：
      - `Feishu signature -> gateway -> main-agent -> worker poll -> Ralph -> review -> notification`
      - 关闭真实 LLM 出口时，链路可完整跑到 `validation failed`
    - 真实 MiniMax 调用在本机近真实回测中失败：
      - `RuntimeError: LLM provider is unreachable`
      - 根因表象：`SSL: UNEXPECTED_EOF_WHILE_READING`
  - 已新增能力差异与优化清单计划：
    - `docs/plans/capability-gap-and-optimization-plan.md`
    - 已明确下一轮收敛顺序：
      1. 先压 `Ralph / Review Agent / Worker`
      2. 再收 declarative agent spec
      3. 再收 event / memory 边界
  - 已完成 `Round Next-A` 第一版：
    - 新增 `app/agents/ralph/drafting.py`
    - 新增 `app/agents/ralph/github_bridge.py`
    - 新增 `app/agents/code_review_agent/store.py`
    - worker 实现已迁到 `app/control/sleep_coding_worker.py`
    - `app/services/sleep_coding_worker.py` 已降为 facade
    - 已删除旧计划文档：
      - `docs/plans/mvp-architecture-convergence-plan.md`
      - `docs/plans/mvp-multi-round-execution-plan.md`
  - 本轮测试结果：
    - 高相关回归通过
    - 全量测试通过：
      - `python -m unittest discover -s tests -v`
      - `110 tests OK`
  - 已完成 `Round Next-A` 第二版：
    - 新增 `app/agents/ralph/store.py`
    - 新增 `app/agents/code_review_agent/bridge.py`
    - 新增 `app/agents/code_review_agent/context.py`
    - 新增 `app/control/sleep_coding_worker_store.py`
    - `app/agents/ralph/application.py` 已把 task persistence / event serialization / load 逻辑下沉到 store
    - `app/agents/code_review_agent/application.py` 已把 review writeback / review context 组装下沉到 bridge/context helper
    - `app/control/sleep_coding_worker.py` 已把 claim schema / lease / retry / attach / list 下沉到 worker store
    - 复杂度压缩结果：
      - `ralph/application.py`: `1293 -> 995`
      - `code_review_agent/application.py`: `902 -> 779`
      - `sleep_coding_worker.py`: `735 -> 504`
  - 最新测试结果：
    - 高相关回归：
      - `python -m unittest tests.test_sleep_coding tests.test_review tests.test_sleep_coding_worker tests.test_api tests.test_automation tests.test_mvp_e2e -v`
      - `60 tests OK`
    - 全量回归：
      - `python -m unittest discover -s tests -v`
      - `110 tests OK`
  - 已完成 `Round Next-B` 第一版：
    - `app/core/config.py`
      - 新增 `AgentSpec`
      - 新增 `Settings.resolve_agent_spec(agent_id)`
    - `app/runtime/agent_runtime.py`
      - `AgentDescriptor` 已支持 `from_spec`
      - prompt 已显式注入 `memory_policy / execution_policy`
      - workspace instructions 已纳入 `SOUL.md`
    - `agents.json`
      - 已补 `system_instruction / memory_policy / execution_policy`
    - 三个 agent workspace 已补：
      - `agents/main-agent/SOUL.md`
      - `agents/ralph/SOUL.md`
      - `agents/code-review-agent/SOUL.md`
    - `main-agent / ralph / code-review-agent` 的 descriptor 构建已统一切到 `settings.resolve_agent_spec(...)`
  - 最新测试结果：
    - 高相关回归：
      - `python -m unittest tests.test_runtime_components tests.test_main_agent tests.test_sleep_coding tests.test_review tests.test_api tests.test_automation tests.test_mvp_e2e -v`
      - `67 tests OK`
    - 全量回归：
      - `python -m unittest discover -s tests -v`
      - `111 tests OK`
  - 已完成 `Round Next-C` 第一版：
    - `app/control/events.py`
      - 已新增显式 domain event 常量：
        - `issue.created`
        - `task.claimed`
        - `plan.ready`
        - `review.completed`
        - `review.approved`
        - `review.changes_requested`
        - `delivery.completed`
        - `sleep_coding.follow_up.requested`
        - `follow_up.queued / processing / completed / failed`
    - `app/services/task_registry.py`
      - 已新增 `append_domain_event(...)`
    - `app/services/automation.py`
      - follow-up / delivery 主链路已开始追加 domain events
      - legacy event names 继续保留，避免打碎兼容性
    - `app/services/session_registry.py`
      - 已新增 `append_short_memory(...)`
      - 已新增 `list_short_memory(...)`
      - `short_memory_summary` 继续兼容，`short_memory_entries` 成为更稳定的轻量 facade
    - `app/control/context.py`
      - short-memory 读写已统一走 `SessionRegistryService`
  - 最新测试结果：
    - 高相关回归：
      - `python -m unittest tests.test_control_context tests.test_session_registry tests.test_task_registry tests.test_automation tests.test_mvp_e2e tests.test_api tests.test_sleep_coding_worker -v`
      - `44 tests OK`
    - 全量回归：
      - `python -m unittest discover -s tests -v`
      - `112 tests OK`
  - 已继续完成 `Round Next-C` 收尾压缩：
    - `app/services/automation.py`
      - 已从 `528 -> 280`
    - 新增 `app/control/follow_up.py`
      - follow-up scheduling / state transition / event append 已从主编排剥离
    - 新增 `app/channel/delivery.py`
      - manual handoff / final delivery 文案组装已从主编排剥离
  - 最新测试结果：
    - 高相关回归：
      - `python -m unittest tests.test_automation tests.test_api tests.test_mvp_e2e tests.test_sleep_coding_worker -v`
      - `39 tests OK`
    - 全量回归：
      - `python -m unittest discover -s tests -v`
      - `112 tests OK`
  - 已补最新验收闭环：
    - 全量回归再次通过：
      - `python -m unittest discover -s tests`
      - `114 tests OK`
    - 真实 Feishu 出站验证已确认：
      - 使用 `ChannelNotificationService.notify(...)`
      - 返回：`{'provider': 'feishu', 'delivered': True, 'is_dry_run': False}`
      - 实发标题：`Youmeng Gateway 全链路验证`
    - 真实 GitHub MCP 写链路再次确认：
      - 最新验证样本：`issue #45`
      - 最新 PR：`PR #46`
      - issue 评论已出现 `Ralph PR Ready`
    - 这次真实外部链路可确定跑到：
      - `Feishu inbound -> gateway -> issue -> claim -> coding -> PR Ready -> Feishu outbound`
    - 仍未确认的一点：
      - 同一批真实样本尚未核实到 `review approved -> final delivery completed`
      - 因此后续若继续做“全外部系统闭环”验收，优先补 review/final delivery 收尾，而不是重复创建 issue/PR

## 2. 已做出的关键决策

- 文档层只保留当前 MVP 有效事实来源，不再在当前分支保留历史 phase 文档或中间迁移方案。
- `docs/review-runs/` 是运行时产物目录，不再纳入版本控制。
- GitHub/GitLab 外部写操作坚持 MCP-only，配置入口坚持 `mcp.json`，不回退 REST / `GITHUB_TOKEN`。
- 配置继续保持 JSON-first：
  `agents.json / models.json / platform.json / mcp.json`
- LLM 请求层统一 timeout/retry 已在 shared runtime 中实现：
  默认 3 次尝试 + 指数退避，配置来源是 `platform.json`。
- 入口编排已决定彻底收口到 control plane，不再恢复 `LangGraph WorkflowRunner`
- 当前事件驱动收敛策略是“轻量本地 event bus + persisted control events”，不前置外部消息队列
- agent application modules 已决定作为显式目录边界保留；旧 `services/*` 仅在过渡期作为 facade 存在
- 当前短记忆策略已决定为“session payload summary + context assembly”，不前置向量库或复杂检索
- 当前 infra / channel 策略已决定为：主路径直接依赖 `app/channel/*` 与 `app/infra/*`，`services/*` 只保留领域服务和兼容 facade
- 新一轮改造策略已决定为：优先压缩“可压缩复杂度”，不触碰 issue/claim/review/delivery 状态机等必要复杂度
- `Round Next-A` 已完成，且保持了 `SleepCodingService / ReviewService / WorkerService` 对外接口不变
- `Round Next-B` 已完成：agent spec 已收口为 `agents.json -> resolve_agent_spec -> AgentDescriptor.from_spec`
- `Round Next-C` 已完成：control event 语言与 short-memory facade 已完成第一版收口
- `Round Next-C` 收尾压缩已完成：`automation` 主编排已显著收薄，follow-up / delivery 已拆出稳定边界
- 真实 Feishu 出站、GitHub issue/PR 写链路、全量测试都已再次核实
- 每完成一个阶段，必须同步更新：
  - `docs/status/current-status.md`
  - `docs/status/session-handoff.md`

## 3. 用户偏好与约束

- 用户偏好：
  - 多 agent 架构
  - `LLM + MCP + skill` 优先
  - JSON-first
  - 骨架要尽量接近 `nanobot/OpenClaw` 的极简形态：`channel -> control plane -> runtime -> agent`
  - Agent 行为优先通过 `AGENTS.md / TOOLS.md / SOUL.md` 等工作区指令定义
  - 不要把实际配置文件提交进仓库
  - 当前 PR 要尽量减压、避免“大平台全集”式膨胀
- 用户明确接受的处理顺序：
  1. 先清理文档噪音
  2. 再评估代码侧哪些非主链路能力能安全剥离
- 当前不要做的事：
  - 不要重新引入 REST fallback
  - 不要把未来 domain agent（Novel/TCM/Metaphysics）相关规划重新带回当前 PR
  - 不要为了缩 PR 乱删主链路核心代码


## 5. 关键参考信息

- 当前主事实来源：
  - `docs/status/current-status.md`
  - `docs/status/session-handoff.md`
  - `docs/plans/capability-gap-and-optimization-plan.md`
  - `docs/plans/mvp-execution-plan.md`
  - `docs/requirements/mvp-gap-analysis.md`
  - `docs/architecture/mvp-agent-first-architecture.md`
  - `docs/architecture/github-issue-pr-state-model.md`
- 与当前判断直接相关的代码：
  - `app/control/gateway.py`
  - `app/control/events.py`
  - `app/control/context.py`
  - `app/agents/main_agent/application.py`
  - `app/agents/ralph/application.py`
  - `app/agents/code_review_agent/application.py`
  - `app/main.py`
  - `app/api/routes.py`
  - `app/services/automation.py`
  - `app/services/feishu.py`
  - `tests/test_api.py`
  - `tests/test_automation.py`
  - `tests/test_mvp_e2e.py`
- 当前分支：`codex/mvp-architecture-plan`
- 当前工作树状态：
  - 已有结构改动未提交
  - 本轮还同步修改了文档与测试
- 最近相关提交（提交前基线）：
  - `48ab6ae` `Trim non-essential MVP docs from branch`
  - `32a4993` `Prune historical docs and review artifacts`
  - `b3b957d` `Finalize agent-first MVP runtime and workflow`
  - `580c9e9` `Tighten LLM failure handling for agent workflow`

## 6. 当前状态检查

- 这份交接文档已根据 `codex/mvp-architecture-plan` 的 4 轮收敛结果更新。
- 下一位 LLM 若继续，优先顺序应为：
  1. 看 `git status`
  2. 看 `docs/status/current-status.md`
  3. 看 `docs/plans/capability-gap-and-optimization-plan.md`
  4. 看 `docs/plans/mvp-execution-plan.md`
  5. 默认继续进入下一轮复杂度压缩：
     - 避免 domain event / short-memory facade / follow-up / delivery 再回流到厚 application 文件
     - 继续压缩 `Ralph / Review Agent` 的可压缩复杂度
     - 本轮不并行做 MiniMax 真实链路排障
