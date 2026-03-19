# 能力差异与优化清单

> 更新时间：2026-03-19
> 目标：围绕 `channel -> control plane -> runtime -> agent` 的极简骨架，对当前 `youmeng-gateway` 与 `nanobot/OpenClaw/opencode` 风格的差距做收口计划，明确哪些复杂度必须保留，哪些必须压缩，以及下一轮改造顺序。

## 进度更新

- `Round Next-C` 第一版已完成，目标未偏移。
- 本轮只收口 control event 语言与 short-memory facade，没有扩展新能力面：
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
    - legacy event names 继续保留，避免打碎现有链路与测试
  - `app/services/session_registry.py`
    - 已新增 `append_short_memory(...)`
    - 已新增 `list_short_memory(...)`
    - `short_memory_summary` 继续兼容，`short_memory_entries` 成为更稳定的轻量 facade
  - `app/control/context.py`
    - short-memory 读写已统一走 `SessionRegistryService` facade
- 本轮验收已通过：
  - 高相关回归：`44 tests OK`
  - 全量回归：`112 tests OK`
- 结论：
  - `Round Next-C` 第一版可视为完成
  - 当前下一轮应进入“继续压缩可压缩复杂度”，而不是再扩新能力面
- `Round Next-C` 完成后已继续做一轮复杂度压缩：
  - `app/services/automation.py`
    - 已从 `528 -> 280`
  - 新增 `app/control/follow_up.py`
    - follow-up scheduling / state transition / event append 已从主编排剥离
  - 新增 `app/channel/delivery.py`
    - manual handoff / final delivery 文案组装已从主编排剥离
- 追加验收已通过：
  - 高相关回归：`39 tests OK`
  - 全量回归：`112 tests OK`

- `Round Next-B` 第一版已完成，目标未偏移。
- 本轮只收口 declarative agent spec 与 workspace docs 装配，没有扩展新链路：
  - `app/core/config.py`
    - 新增 `AgentSpec`
    - 新增 `Settings.resolve_agent_spec(agent_id)`
  - `app/runtime/agent_runtime.py`
    - `AgentDescriptor` 已支持 `from_spec`
    - prompt 已显式注入 `memory_policy / execution_policy`
    - workspace docs 装配已纳入 `SOUL.md`
  - `agents.json`
    - 已补 `system_instruction / memory_policy / execution_policy`
  - `app/agents/main_agent/application.py`
  - `app/agents/ralph/drafting.py`
  - `app/agents/code_review_agent/application.py`
    - 已统一切到 `settings.resolve_agent_spec(...)`
- 本轮还补齐了：
  - `agents/main-agent/SOUL.md`
  - `agents/ralph/SOUL.md`
  - `agents/code-review-agent/SOUL.md`
- 本轮验收已通过：
  - 高相关回归：`67 tests OK`
  - 全量回归：`111 tests OK`
- 结论：
  - `Round Next-B` 第一版可视为完成
  - 默认下一轮进入 `Round Next-C`，继续收口 control event 与 memory 边界

- `Round Next-A` 第二版已完成，目标未偏移。
- 本轮只继续压缩三个复杂度黑洞，没有扩展新能力面：
  - `app/agents/ralph/application.py`
    - 持久化与 task/event 反序列化已拆到 `app/agents/ralph/store.py`
  - `app/agents/code_review_agent/application.py`
    - review comment writeback 已拆到 `app/agents/code_review_agent/bridge.py`
    - review context assembly 已拆到 `app/agents/code_review_agent/context.py`
  - `app/control/sleep_coding_worker.py`
    - claim schema / lease / retry / attach / list 已拆到 `app/control/sleep_coding_worker_store.py`
- 当前厚度变化：
  - `ralph/application.py`: `1293 -> 995`
  - `code_review_agent/application.py`: `902 -> 779`
  - `sleep_coding_worker.py`: `735 -> 504`
- 本轮验收已通过：
  - 高相关回归：`60 tests OK`
  - 全量回归：`110 tests OK`
- 结论：
  - `Round Next-A` 可视为完成
  - 默认下一轮进入 `Round Next-B`，开始收口 declarative agent spec 与 `SOUL.md`

## 一、结论先行

当前 4 轮结构收敛已经让项目方向基本对齐你的目标，但还没有达到 `nanobot` 那种“小内核、高内聚、强默认路径”的实现密度。

当前代码的主要问题不是“方向错了”，而是“复杂度还没有被压缩到少数稳定边界”：

- 主骨架已经基本正确：
  - `channel -> control plane -> runtime -> agent`
- 认知路径已经基本正确：
  - `LLM + MCP + skill`
- 但实现密度还不够：
  - 仍有较厚的 agent application files
  - 仍有明显的 domain-heavy worker / registry / ledger / orchestration 逻辑
  - `services/*` 仍保留较多过渡性负担

因此，下一轮不应该继续泛化讨论“要不要重构架构”，而应该进入：

```text
复杂度压缩阶段
```

## 二、目标检查

### 1. 当前计划是否符合你的目标

符合，但只符合到“架子正确”，还没完全符合到“实现内聚”。

已经符合的部分：

- 目录方向已开始对齐 `nanobot/OpenClaw`
- control plane 已成为主入口
- runtime 已明确承载 `llm / skills / mcp / agent_runtime`
- agent 已开始显式化为 application modules
- channel / infra 已从大杂烩 service 中抽出

还未完全符合的部分：

- agent 行为仍有较多 Python 逻辑写死，而不是更多由 workspace docs / skill / config 驱动
- `event / task / worker` 还没有收敛成统一的执行语言
- `worker + review + delivery` 的主复杂度还没有压缩成更薄的 execution/control 抽象

### 2. 后续改造必须持续满足的约束

任何下一轮实现，都必须继续满足：

1. 不偏离 `channel -> control plane -> runtime -> agent`
2. 不重新引入 REST fallback
3. 不为了“优雅”破坏当前主链路稳定性
4. 不前置完整 memory/RAG 平台
5. 不引入“大而全”的 framework 化重构
6. 优先压缩可压缩复杂度，而不是动必要复杂度

## 三、能力差异总览

相对 `nanobot` 风格的优秀个人助手框架，当前项目的主要差异如下：

### A. 已基本具备

- 多 agent 角色边界
- channel / control / runtime / agent 基本层次
- MCP-first 的外部系统写操作
- session / task / event / token ledger 等控制面基础设施
- workspace + skill + MCP 的认知执行路径

### B. 仍明显不足

- 统一 agent loop 不够薄
- declarative agent spec 不够完整
- event 语言还不是第一公民
- worker / review / delivery 仍偏业务态服务，不够像统一执行内核
- memory 只是挂点，不是完整边界
- `services/*` 仍残留较多兼容和过渡负担

### C. 与 `nanobot` 的关键差别

- `nanobot` 更像一个通用 assistant kernel
- 当前项目更像一个已经产品化的 GitHub coding workflow
- `nanobot` 的复杂度更多压在统一 loop / bus / session / channel/provider
- 当前项目的复杂度更多压在特定 domain 状态机：
  - issue intake
  - claim / lease / retry
  - coding / validation
  - review / repair
  - final delivery

这意味着：

- 当前项目的代码量比 `nanobot` 大，不全是坏事
- 真正的问题不是“为什么更大”，而是“大出来的部分里哪些是必要复杂度，哪些是结构没有收干净”

## 四、能力差异与优化清单

说明：

- `必要复杂度`：当前产品目标必须保留，不能为了缩代码量随便砍
- `可压缩复杂度`：应该通过重构、合并、抽象或 declarative 化继续压缩
- `对应代码文件`：当前最主要的入口文件，不代表只能改这些文件

| 优先级 | 能力差异 | 必要复杂度 | 可压缩复杂度 | 对应代码文件 |
| --- | --- | --- | --- | --- |
| P0 | Ralph 承担过厚的 planning + execution + delivery + repair 编排 | 需要保留 sleep-coding 领域状态机 | 单文件过厚、职责过多，应该拆成 planning/execution/delivery 子模块 | `app/agents/ralph/application.py` |
| P0 | Code review agent 同时承载 skill runner、review persistence、comment writeback、task action | 需要保留 review 独立能力 | 需要拆成 review runner / review store / review action bridge | `app/agents/code_review_agent/application.py` |
| P0 | Worker 仍以业务 service 形态存在，claim/lease/retry 复杂度未收口 | 需要保留 worker lease/heartbeat/retry | 应迁到更清晰的 control execution 边界，压缩 service-style 负担 | `app/services/sleep_coding_worker.py` |
| P0 | agent spec 仍有较多运行时信息散落在 settings resolver 和 service init 中 | 需要保留 agent 差异化配置 | 应收口成统一 declarative agent spec：workspace/skills/mcp/model/memory policy | `app/runtime/agent_runtime.py`, `app/core/config.py`, `agents.json` |
| P0 | `services/*` 仍保留较多兼容层，影响一层结构可读性 | 需要保留少量兼容 facade 防止一次性打碎调用 | 继续清理无价值 facade，减少新代码对 `services/*` 的依赖 | `app/services/*.py` |
| P1 | control event 已存在，但还不是主执行语言 | 需要保留 persisted task/event/session | 应把 `issue.created / task.claimed / plan.ready / review.completed / delivery.completed` 变成显式 domain events | `app/control/events.py`, `app/services/automation.py`, `app/services/task_registry.py` |
| P1 | short memory 只是 summary 挂点，不是统一 memory abstraction | 需要保留当前轻量 memory 路径 | 应在不引入向量库前提下补 memory facade 和 assembly policy | `app/control/context.py`, `app/services/session_registry.py` |
| P1 | workspace doc 对 agent 行为的塑形还不够强 | 需要保留当前 runtime prompt assembly | 应正式纳入 `SOUL.md`，并让 agent 更少依赖写死逻辑 | `app/runtime/agent_runtime.py`, `agents/*/AGENTS.md`, `agents/*/TOOLS.md` |
| P1 | token ledger 与业务编排存在较强耦合 | 需要保留 request-level token accounting | 应继续下沉为更薄的 infra contract，减少 agent/service 对账本细节感知 | `app/ledger/service.py`, `app/services/automation.py`, `app/control/gateway.py` |
| P2 | channel 当前仍偏围绕现有 workflow 设计 | 需要保留 Feishu 入口与通知能力 | 应继续抽象为真正可插拔的 channel adapter | `app/channel/feishu.py`, `app/channel/notifications.py` |
| P2 | runtime 仍偏“工具集合”，还不是统一 run engine | 需要保留现有 runtime 目录边界 | 可逐步抽成统一 `AgentLoop/RunEngine`，但不作为下一轮首要任务 | `app/runtime/agent_runtime.py`, `app/runtime/llm.py`, `app/runtime/mcp.py`, `app/runtime/skills.py` |
| P2 | diagnostics/scheduler/background jobs 仍偏工程支撑件，尚未完全统一 execution model | 需要保留现有运维和后台能力 | 可后续进一步靠拢统一 execution plane，但不应早于 P0/P1 | `app/infra/*.py` |

## 五、改造顺序

下一轮建议顺序不能乱，必须按“先压黑洞，再收 declarative，再补 event/memory”的顺序推进。

### Step 1. 先压主复杂度黑洞

目标：

- 先拆最厚、最影响可读性的文件

顺序：

1. `ralph/application.py`
2. `code_review_agent/application.py`
3. `sleep_coding_worker.py`

原因：

- 这些文件是当前复杂度最集中的位置
- 不先拆它们，后面谈 declarative agent spec 或统一 event 语言都容易继续堆回大文件

完成标准：

- 不改变对外行为
- 不改变主链路状态机语义
- 只做“按职责拆薄”

### Step 2. 再收 agent spec

目标：

- 让 agent 的差异更多由 declarative spec 决定，而不是散落在 Python init 和 settings resolver

要收口的字段：

- `agent_id`
- `workspace`
- `skills`
- `mcp_servers`
- `model_profile`
- `memory_policy`
- `execution_policy`

完成标准：

- 主路径上新增 agent 时，不需要复制大量 service 初始化模式
- workspace docs 对行为的塑形作用进一步增强

### Step 3. 再收 event 语言

目标：

- 让 control plane 真正用统一 domain event 描述链路推进

范围：

- issue intake
- task claim
- plan ready
- review completed / blocked
- final delivery

完成标准：

- 后台 follow-up 和 review/delivery 的推进，不再主要靠 service 之间直接串调用表达

### Step 4. 最后补 memory 边界

目标：

- 在不引入 RAG 的前提下，把 memory 做成稳定接口

范围：

- short memory facade
- assembly policy
- future long-memory interface placeholder

完成标准：

- 后续接长记忆时，不需要重写 control plane 或 agent application 层

## 六、下一轮推荐执行计划

### Round Next-A. 压缩主复杂度黑洞

本轮只做：

1. 拆 [Ralph] 相关 application 文件
2. 拆 [Review Agent] 相关 application 文件
3. 迁移或重命名 worker 边界
4. 清理在此过程中自然退出主路径的 facade/import

本轮不做：

- 长记忆
- 新 channel
- 新 domain agent
- 新 MQ
- 大规模 runtime 重写

验收标准：

- 主链路测试通过
- 文件厚度明显下降
- 一层结构更容易让新 agent 接手

### Round Next-B. 收口 declarative agent spec

本轮只做：

1. 统一 agent spec
2. 接入 `SOUL.md`
3. 减少 service init 里的 agent-specific wiring

本轮不做：

- runtime engine 大重写
- memory 平台化

### Round Next-C. 收口 event 与 memory 边界

本轮只做：

1. 补 domain event 命名和 handler 边界
2. 把 short memory 升为正式 facade
3. 给 future long-memory 留接口

## 七、持续检查机制

后续每次编码前，必须先过以下检查。

### Check 1. 目标是否偏移

若本轮改动不能直接解释为以下之一，则说明偏移：

- 压缩可压缩复杂度
- 提升 agent 内聚度
- 强化 declarative agent spec
- 强化 control event 语言
- 强化 memory 边界

### Check 2. 是否错误触碰必要复杂度

以下能力属于必要复杂度，不能为了“像 nanobot”乱砍：

- issue -> claim -> coding -> review -> final delivery 状态机
- lease / heartbeat / retry
- MCP-only 外部写操作
- token ledger
- control task / event / session 可观测性

### Check 3. 是否重新把复杂度堆回 service

任何新增复杂逻辑，如果落回：

- `app/services/automation.py`
- `app/services/*` 兼容 facade
- `app/api/routes.py`

都应先停下来复查边界。

### Check 4. 是否仍然符合目标要求

每轮结束必须明确回答：

1. 是否更接近 `channel -> control plane -> runtime -> agent`
2. 是否更接近 workspace/skill/config 驱动，而不是 Python 写死
3. 是否没有引入新平台负担
4. 是否没有破坏主链路

## 八、文档纪律

本计划是下一轮收敛的总基线。

后续要求：

1. 编码前先引用本计划，确认本轮只做哪一部分
2. 编码后必须跑测试
3. 每完成一轮必须更新：
   - `docs/status/current-status.md`
   - `docs/status/session-handoff.md`
4. 若实现方向偏移，先改本计划，再继续编码

## 九、下一步

默认下一步不是直接编码全部优化项，而是：

1. 确认本计划
2. 进入 `Round Next-A`
3. 只做：
   - `Ralph / Review Agent / Worker` 三个复杂度黑洞的压缩
4. 编码前再做一次目标检查
5. 编码后跑全量测试
6. 更新状态文档

## 十、当前进度

### Round Next-A

状态：

- 已完成第一版

本轮已完成：

1. Ralph drafting / GitHub bridge 已拆到独立辅助模块：
   - `app/agents/ralph/drafting.py`
   - `app/agents/ralph/github_bridge.py`
2. `SleepCodingService` 保持对外接口不变，但主文件已把 draft/build/render/GitHub 写操作委托给 helper
3. Review Agent 已拆出 store / source support：
   - `app/agents/code_review_agent/store.py`
4. worker 实现已迁到更清晰的 control 边界：
   - `app/control/sleep_coding_worker.py`
   - `app/services/sleep_coding_worker.py` 已降为 facade
5. 已删除已完成且会形成双事实源的旧计划文档：
   - `docs/plans/mvp-architecture-convergence-plan.md`
   - `docs/plans/mvp-multi-round-execution-plan.md`

本轮未完成：

1. `Ralph / Review Agent / Worker` 还没有拆到最终目标粒度
2. declarative agent spec 还未启动
3. event / memory 的下一轮收口还未启动

本轮验证：

- 高相关回归已通过
- 全量测试已通过：
  - `python -m unittest discover -s tests -v`
  - `110 tests OK`
