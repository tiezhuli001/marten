# MVP Execution Plan

> 更新时间：2026-03-18
> 目标：基于 `mvp-gap-analysis.md`，分阶段收口到可用 MVP。

## 一、计划目标

本计划不再按 `Phase 0 / 1 / 2 / 3 / 4` 迭代视角推进，而是按“离可用 MVP 还差什么”来推进。

同时，本计划参考 OpenClaw 的核心架构思路：

- Gateway 作为控制平面
- Channel Adapter 与 Agent Runtime 解耦
- Shared Runtime 复用 provider / skill / MCP / tools
- Agent 只表达角色、上下文和权限边界
- 配置层采用 JSON-first，`.env` 只保留 secrets 与基础运行参数

最终目标是形成这样一条真实闭环：

```text
Feishu 用户提需求
-> 主 Agent 理解需求并创建 GitHub issue
-> Sleep Coding Worker 发现 issue
-> 生成计划并通知用户
-> LLM + skill + MCP 编码
-> 自动提交 PR
-> 自动触发 Code Review
-> 最多 3 轮修复
-> 输出最终结果 + token 消耗 + review 结论到 Feishu
```

## 二、执行原则

### 工程层

必须由确定性代码实现：

- provider 配置
- token/cost 记账
- Feishu 鉴权与事件接入
- GitHub / GitLab / MCP 连接配置
- `agents.json / models.json / platform.json / mcp.json` 的加载与默认值策略
- scheduler / polling / retry / timeout
- task / review / repair loop 状态机

### 智能层

优先交给 LLM + skill + MCP：

- issue 生成
- plan 生成
- 编码实现
- review 生成
- repair 决策
- 最终总结文案

## 三、目标结构

MVP 的推荐结构应固定为：

1. `Gateway`
2. `Channel Layer (Feishu)`
3. `Shared Agent Runtime`
4. `Main Agent`
5. `Ralph`
6. `Code Review Agent`
7. `Shared Infra`

后续所有实现都应围绕这 7 个角色展开，而不是继续增加分散的 service 模块。

## 四、实施分段

### MVP-A 真实入口与模型层

目标：让系统真正接入用户与模型。

任务：

1. 增加统一 `LLM provider adapter`
2. 第一版接入 `OpenAI`
3. 第一版接入 `Minimax`
4. 每次模型调用都返回标准化 usage
5. 增加 pricing registry，按 provider+model 计算 `cost_usd`
6. 增加 Feishu 机器人入口 API
7. 完成 Feishu 签名校验、事件解析、用户标识映射

通过标准：

- 用户可通过 Feishu 发消息到 Gateway
- Gateway 可调用 OpenAI / Minimax 至少一类真实模型
- token ledger 可记录真实 usage 和 cost

### MVP-B Main Agent 与 GitHub Issue Intake

目标：把“用户问题 -> GitHub issue”打通。

任务：

1. 增加主 Agent 服务
2. 使用 LLM + skill 生成 issue title / body / labels 草案
3. 接入 GitHub issue 创建能力
4. 接入 GitHub MCP，并以 `mcp.json` 作为唯一配置入口；未配置时默认失败，不再保留 REST fallback
5. issue 创建成功后回写 Feishu 通知

通过标准：

- 用户可从 Feishu 发起需求
- 主 Agent 可在目标 GitHub 仓库创建 issue
- issue 链接可回传给用户

### MVP-C Ralph

目标：把 Sleep Coding 从手动 API 原型升级为真实子 Agent。

任务：

1. 增加 issue polling / scheduled worker
2. 定义“哪些 issue 可被 Sleep Coding 接管”的识别规则
3. 发现 issue 后自动创建 task
4. 生成 plan，并通知用户
5. 将 plan 存档到 task / issue comment / docs artifact
6. 在 worktree 中调用 LLM + skill + MCP 执行编码
7. 保留本地验证、commit、push、PR 打开流程

通过标准：

- worker 可自动发现待处理 issue
- Sleep Coding 可自动从 issue 进入 PR
- plan 和执行痕迹可查询

### MVP-D Code Review Agent 与 Auto Review Loop

目标：实现 Ralph 风格的自动 review / repair 闭环。

任务：

1. PR 打开后自动触发 review agent
2. review 结果写入 PR comment 与 artifact
3. 将 review finding 归类为 `P0/P1/P2/P3`
4. 当存在 `P0/P1` 时自动进入 repair loop
5. 最大修复轮次设为 3
6. 超过 3 轮仍未通过时，转人工并通知用户
7. 当无 `P0/P1` 时进入完成态

通过标准：

- review 不再需要人工单独触发
- repair loop 可自动执行
- 3 轮上限和人工兜底清晰可见

### MVP-E Final Delivery

目标：把最终体验收口到“用户可感知完成”。

任务：

1. 聚合 PR 信息
2. 聚合最终 review 结论
3. 聚合本次 token / cost 消耗
4. 通过 Feishu 发送最终完成通知
5. 明确区分 `real-run` 与 `dry-run`

通过标准：

- 用户收到一次完整的收尾消息
- 消息中包含 issue / PR / review / token / 状态结论

## 五、推荐实施顺序

1. 先做 `MVP-A`，因为没有真实模型和 Feishu 入口，后面都只是原型
2. 再做 `MVP-B`，把对话入口和 GitHub issue intake 打通
3. 再做 `MVP-C`，让 Sleep Coding 真正自动运行
4. 再做 `MVP-D`，把自动 review / repair loop 接上
5. 最后做 `MVP-E`，收口到最终用户体验

## 六、每段的实现方式建议

### 对 LLM 能力的使用

当前模型能力足以承担：

- 需求转 issue
- issue 转 plan
- plan 转代码补丁
- PR review 生成
- review 转 repair strategy

因此后续不建议用大量规则代码替代这些认知工作。

### 对 skill / MCP 的使用

优先方案：

- issue 生成：LLM + issue-writer skill + GitHub MCP
- 编码执行：LLM + coding skill + 本地 git/worktree tool + GitHub MCP
- code review：LLM + code-review skill + GitHub/GitLab/local context

Fallback 方案：

- MCP 不可用时，保留 REST API fallback

### 对成熟库的偏好

为避免过度工程化，后续优先选择成熟库，而不是继续手写大量集成层：

- `FastAPI`: Gateway / Feishu webhook API
- `httpx`: 统一 HTTP client
- `APScheduler`: polling / cron / heartbeat
- `openai` 官方 SDK: OpenAI provider
- `MiniMax` 官方 SDK 或稳定 HTTP API 封装: MiniMax provider
- `MCP Python SDK`: MCP 集成

## 七、第一轮优先事项

如果按最小增量推进，下一轮应只做三件事：

1. 统一模型执行层和 token/cost 精确记账
2. Feishu 真实入口
3. GitHub issue 创建链路

原因：

- 这是后续所有 agent 行为的前提
- 没有这三项，Sleep Coding 和 Auto Review 仍只是手动原型

## 八、验收口径

只有满足下面这些条件，才可称为目标 MVP：

- 用户通过 Feishu 对话触发真实任务
- 系统可创建 GitHub issue
- Sleep Coding 可自动发现并处理 issue
- PR 可自动触发 Code Review
- review / repair loop 最多执行 3 轮
- 系统可输出真实 token / cost 统计
- 最终结果可通过 Feishu 回传

## 九、当前执行落点（2026-03-18）

当前主线目标没有偏移，仍然是：

- 保持 `Gateway + main-agent + ralph + code-review-agent + shared runtime`
- 保持 JSON-first：`agents.json / models.json / platform.json / mcp.json`
- 在真实环境下把 issue -> PR -> review -> repair -> notify 主闭环做稳

截至 2026-03-18，已经额外确认/完成：

- 主闭环已经真实跑通，不再是只靠 dry-run 的原型验证
- GitHub MCP、review、Feishu 已完成真实联调样本验证
- token ledger 的 `record_request` SQL 插入错误已修复
- `sleep_coding` plan / execution usage 已改为在主事务提交后追加到账本，避免 SQLite 锁等待
- 最终通知中的 token/cost 已按表格化格式输出，作为后续统一展示口径

接下来优先做的不是扩模块，而是继续收口：

1. task / review / final delivery 三处 token 展示的一致性
2. HTTP 长请求的同步/异步边界，避免响应体验和底层状态迁移脱节
3. worker stuck-task 扫描与人工接管能力
