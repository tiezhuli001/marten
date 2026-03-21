# 2026-03-20 Post MVP Slimming Cleanup Plan

> 目标：在当前 MVP 主链已经稳定后，继续删除剩余历史代码、历史文档和冗余抽象。

## 当前状态（2026-03-21）

- Batch 1-5 在当前 MVP 范围内已完成收口。
- `ReviewSource` 已从主模型、主持久化读写和自动化主链移除，review 统一回到 task-derived `ReviewTarget`。
- worker claim / follow-up 主状态已优先跟随 `control_tasks` 投影，而不是直接依赖 `sleep_coding_tasks` 作为编排真相。
- `models.json` provider 读取已收为 canonical snake_case key。
- `mvp-agent-first-architecture` 已迁到 `docs/archive/architecture/`，公开入口改为 `mvp-agent-platform-core`。

## Batch 1: 旧兼容层继续收口

- 删除 review artifact / delivery / 说明文字里残留的非 GitHub 语义。
- 继续审计 `app/agents/code_review_agent/`，把只服务于历史多来源 review 的兜底分支删到最小。
- 清理 `artifacts/` 的测试产物处理策略，明确本地忽略和 CI 行为。
- 把 review 对外 contract 收到只接受 `task_id`，其余 `repo/pr_number/url/local_path/base_branch/head_branch` 全部内部派生。

## Batch 2: 控制面薄层合并

- 评估 [automation.py](/Users/litiezhu/workspace/github/marten/app/control/automation.py)、[gateway.py](/Users/litiezhu/workspace/github/marten/app/control/gateway.py)、[routing.py](/Users/litiezhu/workspace/github/marten/app/control/routing.py) 的职责边界。
- 把纯转发型薄层下沉回真正的 owner 模块，减少“控制面里再包一层控制面”的情况。
- 保持 `GatewayRoute`、session registry、task registry 这些核心 contract，不做伤筋动骨的大改。
- 直接写入口已下线：
  - `POST /tasks/sleep-coding`
  - `POST /reviews`
  - task/review action 旁路接口
  当前保留读接口，避免重新引入绕开 `gateway -> main-agent -> ralph -> review` 主链的写接口。

## Batch 3: Ralph 主链再减重

- 盘点 Ralph 中 plan、execution、progress、store 之间是否还有重复状态写回。
- 审计事件写入，删除只为历史观察链路保留、但不再被消费的事件。
- 对 `sleep_coding_*` 相关 schema 做第二轮收缩，只保留当前主链真正会被读取的字段。
- 明确 `control_tasks + control_task_events` 是否升级为唯一控制真相，逐步降低 `sleep_coding_tasks` / `review_runs` 对主编排的驱动作用。

## Batch 4: 文档归档

- 以 [mvp-agent-platform-core.md](/Users/litiezhu/workspace/github/marten/docs/architecture/mvp-agent-platform-core.md) 为主文档。
- 将旧阶段设计文档拆成三类：保留、改写、归档。
- 对仍保留的架构文档统一加上“当前真实实现”范围说明，避免继续误导后续迭代。
- 将 [mvp-agent-first-architecture.md](/Users/litiezhu/workspace/github/marten/docs/archive/architecture/mvp-agent-first-architecture.md) 视为历史方案稿，已迁到归档位。

## Batch 5: 面向未来演进的扩展位校准

- 在不破坏 MVP 核心的前提下，为 agent registry、json agent config、per-agent MCP 绑定保留最小扩展点。
- 先不做多任务并发调度和复杂 memory，只把 contract 留稳。
- 后续新增垂直 agent 时，要求全部挂到同一套 session / routing / handoff contract 上，不再复制主链实现。
- 收紧 provider / model 配置兼容别名，只保留 `models.json` 的 canonical key，必要时提供一次性迁移脚本而不是长期兼容。
