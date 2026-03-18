# MVP Gap Analysis

> 更新时间：2026-03-17
> 目标：对齐“当前实现”与“目标 MVP”之间的差距，作为后续逐步实现的基线文档。

## 一、MVP 目标定义

当前目标 MVP 不是“Phase 0-4 原型闭环”，而是一个可实际使用的第一版个人多 Agent 系统，至少要满足：

1. 配置并调用真实大模型 API，第一版先支持 `OpenAI` 和 `Minimax`
2. 通过 `Feishu` 作为真实对话入口，而不仅是 webhook 出站通知
3. 主 Agent 能根据用户对话，在 GitHub 项目中创建 issue
4. Sleep Coding 子 Agent 能轮询或定时发现 issue，自动启动编码流程
5. 编码后自动开 PR，并自动触发 Code Review 子 Agent
6. Sleep Coding 与 Code Review 形成最多 3 轮的自动修复闭环
7. 最终通过 Feishu 向用户输出结果、review 结论和 token 消耗
8. Code Review 子 Agent 支持 `local / GitHub / GitLab`

## 二、当前实现定位

当前代码库更准确的定位是：

> 多 Agent MVP 主闭环 + 待联调的运行治理增强版

已具备：

- Gateway / FastAPI 统一入口
- Main Agent / Sleep Coding / Code Review 三个核心 Agent
- shared runtime：`llm / skills / mcp / agent_runtime`
- 统一 control tasks / events / sessions 第一版
- Sleep Coding worker / polling / scheduler 第一版
- Code Review structured findings / repair loop 第一版
- Token Ledger / Daily Summary 第一版
- GitHub / GitLab / Feishu webhook 最小集成
- Integration diagnostics：`/diagnostics/integrations`
- Worker governance 第一版：`lease / heartbeat / timeout / retry`

未具备：

- GitHub MCP / review skill / Feishu 的真实环境联调验证
- 更完整的运行治理：stuck-task 扫描、cancel / resume、dead-letter / manual handoff 策略

## 三、LLM / Skill / MCP 与工程代码的边界

结合当前 2026-03-17 的 LLM 常见能力水平，MVP 应按下面的边界建设：

这一边界参考了 OpenClaw 的核心理念：

> 模型负责思考，运行时负责执行。

### 必须工程化的能力

- API key / webhook / token 配置
- Feishu 签名校验与事件接入
- token 使用记录与 cost 账本
- 调度、轮询、重试、超时控制
- task / review / issue / PR 状态机
- 最终通知、幂等控制、失败恢复

### 适合交给 LLM + skill + MCP 的能力

- 用户需求转 issue 草案
- issue 理解与实施计划生成
- 编码与补丁生成
- PR code review 内容生成
- review 结论摘要
- 多轮修复中的“是否继续修”“怎么修”

### 当前阶段的关键判断

- `token ledger` 不应交给 LLM 计算
- `sleep coding` 的 plan / coding / repair loop 应逐步切到 LLM + skill + MCP
- `code review` 的结论生成层可以由 skill 承担，平台只负责编排和留痕

## 四、差距清单

| 模块 | 目标 MVP | 当前状态 | 结论 |
|------|----------|----------|------|
| 模型执行层 | 真实调用 OpenAI / Minimax，并返回可记账 usage | 已有统一 provider adapter，支持 OpenAI / Minimax，返回标准化 usage；但真实线上联调仍待验证 | 基本满足 |
| Token / Cost | 能识别模型并按 provider+model 计算 token/cost | 已支持 provider+model pricing registry 和 usage/cost 入账；但 task / review 级聚合仍可继续加强 | 基本满足 |
| Feishu 入口 | 用户通过 Feishu 机器人发起对话 | 已有 Feishu webhook 入站、验签和事件标准化；但真实会话绑定与线上联调仍未完成 | 部分满足 |
| GitHub Issue 创建 | 主 Agent 可从对话创建 issue | 已支持主 Agent issue intake，并开始迁到 `skill + MCP 优先` 路径 | 基本满足 |
| GitHub MCP | issue / PR 工作流可通过 MCP 执行 | 已接入基于官方 MCP Python SDK 的 stdio adapter 和 GitHub adapter，支持 `mcp.json` 可插拔配置，main-agent / sleep-coding 会优先调用；但真实环境联调仍待验证 | 基本满足 |
| Sleep Coding 触发 | 发现 issue 后自动启动 | 已有 issue polling、claim、scheduled worker 骨架 | 基本满足 |
| Sleep Coding 编码器 | 真实 LLM+skill 执行编码 | plan/coding 已迁到 AgentRuntime + workspace skills，并可生成结构化 file changes；但真实代码修改器和稳定联调仍未完成 | 部分满足 |
| Sleep Coding 调度 | 定时或轮询执行 | 已有独立 worker 调度线程、run-once API，以及 lease / heartbeat / timeout / retry 第一版；线上稳定性和治理仍待真实环境验证 | 基本满足 |
| PR 自动 review | 开 PR 后自动触发 review | 已自动串联到 review agent，并可回写 artifact / comment | 基本满足 |
| 最多 3 轮修复 | review 结果驱动自动再修，3 轮上限后转人工 | 已有 blocking review 判定、自动 repair loop、3 轮上限和人工兜底通知 | 基本满足 |
| 最终 Feishu 汇总 | 输出 PR、review 结论、token 消耗、完成状态 | 已有 final delivery channel 通知与 parent task 回写；真实 Feishu 完整回传联调仍待完成 | 基本满足 |
| 多 Agent 控制面 | parent/child task、事件、session | 已有统一 `control_tasks / control_task_events / control_sessions` 第一版，并接入 main-agent/sleep-coding/review；但还缺更完整的 run supervision | 基本满足 |
| Code Review 输入 | local / GitHub / GitLab 均可 review | 第一版已支持三类输入 | 基本满足 |
| Code Review 执行器 | review 由 skill 驱动 | 已迁到结构化 findings 输出，支持 `summary/findings/repair_strategy/blocking`；但真实环境联调仍待验证 | 基本满足 |

## 五、与 Ralph 目标流程的差距

当前平台与 Ralph 目标流程的主要差距在于：

1. `coding` 已进入 `LLM + skill + MCP` 路径，但真实代码修改器仍未完全收口
2. GitHub MCP 已接入，但真实环境联调和稳定性验证还未完成
3. shared runtime 还没有完全替换掉分散的 service 风格 agent 逻辑
4. 运行治理能力已完成第一版，但仍未完全收口

当前实现更像：

> 已串起主链路的工程骨架，但认知层仍未完全迁到 shared runtime + skill + MCP

目标 MVP 应演进为：

> Feishu 驱动 + GitHub issue/PR 驱动 + shared runtime 承载 skill/MCP/LLM + 工程状态机托底

## 六、OpenClaw 启发下的文档修正结论

参考 OpenClaw 的架构分析，当前 MVP 文档需要明确转向：

1. `Gateway as Control Plane`
2. `Channel Adapter` 与 `Agent Runtime` 解耦
3. `Shared Runtime + Per-Agent Role`，而不是为每个 agent 单独发明一套框架
4. `3 个核心 Agent + 共享 Infra`，而不是先堆很多 service 模块

因此后续文档和实现应以：

- `main-agent`
- `ralph`
- `code-review-agent`
- `gateway`
- `shared-infra`

作为第一层结构，而不是继续以 phase 内部 service 清单作为主视角。

## 七、MVP 实现原则

后续实现 MVP 时，按下面的优先级决策：

1. 账本、通知、调度、幂等、状态机优先工程化
2. issue 理解、计划、编码、review、修复优先走 LLM + skill + MCP
3. 不为了“可控”把本该交给 LLM 的认知工作手写成大量规则
4. 不为了“智能”把本该工程化的账本、状态、认证交给 LLM

## 八、阶段结论

当前代码库：

- 已满足目标 MVP 的代码主链路要求
- 尚需真实环境联调与运行验证，才能作为稳定可用的个人生产系统

下一步重点不再是继续补新的核心模块，而是：

> 以真实环境联调和运行验证为主，收口最后的稳定性与配置细节

推荐的真实环境验证顺序：

1. 配置真实 `mcp.json / agents.json / models.json / platform.json` 与 `.env` secrets，通过 `/diagnostics/integrations` 验证 MCP server 可发现工具
2. 配置真实 review skill 命令或模型凭证，验证 review agent 结构化输出
3. 配置 Feishu inbound / outbound，验证 webhook + 通知闭环
4. 在真实仓库执行一次 issue -> coding -> PR -> review -> final notify 端到端回归
