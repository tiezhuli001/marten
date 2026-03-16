# MVP Gap Analysis

> 更新时间：2026-03-16
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

> 工程骨架 + 可演示的受控原型闭环

已具备：

- Gateway / FastAPI 统一入口
- Sleep Coding task 状态机第一版
- 独立 Code Review Agent 第一版
- Token Ledger / Daily Summary 第一版
- GitHub / GitLab / Feishu webhook 的最小出站集成

未具备：

- 真实 Feishu 对话入口
- 真实模型执行层
- GitHub MCP issue 创建链路
- Sleep Coding 自动轮询 worker
- Code Review 自动修复循环
- 模型级 token/cost 精确计算

## 三、LLM / Skill / MCP 与工程代码的边界

结合当前 2026-03-16 的 LLM 常见能力水平，MVP 应按下面的边界建设：

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
| 模型执行层 | 真实调用 OpenAI / Minimax，并返回可记账 usage | 仅有 `openai_api_key` 配置，无统一 provider adapter，无 Minimax，无真实 usage 采集 | 未满足 |
| Token / Cost | 能识别模型并按 provider+model 计算 token/cost | 仅能存 `model_name/provider/cost_usd` 字段，默认不会自动识别或计算 | 未满足 |
| Feishu 入口 | 用户通过 Feishu 机器人发起对话 | 只有 Feishu webhook 出站通知 | 未满足 |
| GitHub Issue 创建 | 主 Agent 可从对话创建 issue | 当前只支持读取已有 issue / 评论 / PR / 标签 | 未满足 |
| GitHub MCP | issue / PR 工作流可通过 MCP 执行 | 当前使用 GitHub REST API 封装，无 MCP | 未满足 |
| Sleep Coding 触发 | 发现 issue 后自动启动 | 当前仅支持手动 API / 文本触发 | 未满足 |
| Sleep Coding 编码器 | 真实 LLM+skill 执行编码 | 当前只写入 task artifact，不是真实代码修改器 | 未满足 |
| Sleep Coding 调度 | 定时或轮询执行 | 当前无 scheduler / polling worker | 未满足 |
| PR 自动 review | 开 PR 后自动触发 review | 当前 review 能力独立存在，但未自动串联 | 部分满足 |
| 最多 3 轮修复 | review 结果驱动自动再修，3 轮上限后转人工 | 当前没有 repair loop / 轮次计数 / 严重级别门禁 | 未满足 |
| 最终 Feishu 汇总 | 输出 PR、review 结论、token 消耗、完成状态 | 当前无最终聚合通知 | 未满足 |
| Code Review 输入 | local / GitHub / GitLab 均可 review | 第一版已支持三类输入 | 基本满足 |
| Code Review 执行器 | review 由 skill 驱动 | 当前已支持 review skill 命令链路 | 基本满足 |

## 五、与 Ralph 风格流程的差距

当前 Sleep Coding 与 Ralph 风格流程的主要差距在于：

1. 还没有真正的异步 worker / agent loop
2. 还没有“编码 -> review -> 修复 -> review”的自动循环
3. 还没有基于 review 严重级别的自动门禁
4. 还没有真实模型编码器接入
5. 还没有把 issue / PR / review /通知 串成一个长期运行的 agent 流程

当前实现更像：

> 可手动触发的工程原型

目标 MVP 应演进为：

> Feishu 驱动 + GitHub issue/PR 驱动 + LLM/skill/MCP 执行 + 工程状态机托底

## 六、MVP 实现原则

后续实现 MVP 时，按下面的优先级决策：

1. 账本、通知、调度、幂等、状态机优先工程化
2. issue 理解、计划、编码、review、修复优先走 LLM + skill + MCP
3. 不为了“可控”把本该交给 LLM 的认知工作手写成大量规则
4. 不为了“智能”把本该工程化的账本、状态、认证交给 LLM

## 七、阶段结论

当前代码库：

- 适合作为 MVP 的工程底座
- 不足以直接宣称满足目标 MVP

下一步不应继续抽象讨论，而应进入：

> 以差距清单为基线，按优先级逐项实现 MVP 收口计划
