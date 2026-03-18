# Current Status

> 更新时间：2026-03-18
> 当前阶段：多 Agent MVP 主链路已真实跑通，进入主链路验收与 token/cost 口径收口阶段
> 当前目标：先按 `gateway -> issue -> claim -> coding -> review -> final delivery` 收口真实 MVP 链路，并验证 token/cost 计算与输出；运行治理增强项暂不前置扩展

## 当前结论

- 主仓库已经确定：`youmeng-gateway`
- 开发主环境确定为：Linux 服务器
- 当前交互模式确定为：
  - `OpenClaw`: 沟通、进度反馈、飞书入口
  - `OpenCode`: 服务器上的交互式编码助手
  - `LangGraph + LangSmith`: 第一阶段编排与观测方案

## 已完成

- [x] 主仓库创建并拉取到本地
- [x] 正式迭代计划完成
- [x] `docs/` 目录骨架初始化
- [x] Phase 0 / Phase 1 执行 Plan 完成
- [x] Phase 1 平台骨架代码完成并阶段性提交
- [x] Phase 1 验收基线完成
- [x] Phase 2 第一版 Ralph task/API/workflow 落地
- [x] Phase 2 Ralph 标签策略落地
- [x] Phase 2 Channel 出站通知骨架落地
- [x] Phase 2 git worktree / commit / push dry-run 骨架落地
- [x] Phase 2 worktree 任务产物生成骨架落地
- [x] Phase 2 PR #3 code review 归档并回写处置结果
- [x] Phase 3 文档校准为 skill 驱动 review 方案
- [x] Phase 4 文档补充整体 MVP 验证目标
- [x] Phase 3 独立 review 入口与运行产物目录设计落地
- [x] Phase 3 独立 code review agent 最小能力完成
- [x] Phase 4 implementation plan 归档
- [x] Phase 4 token ledger 扩展字段落地
- [x] Phase 4 7d / 30d token 查询接口落地
- [x] Phase 4 daily token summaries 聚合表落地
- [x] Phase 4 昨日日报生成入口落地
- [x] Phase 0-4 MVP 验证清单归档
- [x] MVP 差距清单归档
- [x] MVP 执行计划归档
- [x] MVP agent-first 架构文档归档
- [x] MVP-A 第一版 OpenAI / Minimax provider adapter 落地
- [x] MVP-A 第一版 Feishu webhook 入站与验签骨架落地
- [x] MVP-B Main Agent issue intake 第一版落地
- [x] MVP-C issue polling / worker claim / scheduled worker 骨架落地
- [x] MVP-D PR 自动触发 review / repair loop / 3 轮上限骨架落地
- [x] MVP-E final delivery channel 通知骨架落地
- [x] shared runtime 第一版目录落地：`llm / skills / mcp / agent_runtime`
- [x] main-agent 第一版迁移到 `skill + MCP`
- [x] shared runtime 已接入官方 MCP Python SDK 的 stdio adapter
- [x] GitHub MCP adapter 第一版落地：`get_issue / create_issue / create_issue_comment / apply_labels / create_pull_request`
- [x] Ralph 已迁到 `AgentRuntime + workspace skills + MCP 优先`
- [x] Ralph coding draft 已支持结构化 `artifact_markdown + file_changes + commit_message`
- [x] code-review 已迁到结构化 findings 输出：`summary + findings + repair_strategy + blocking`
- [x] SkillLoader 已补 OpenClaw 风格 `metadata.openclaw.requires` gate 机制
- [x] 统一 control plane 第一版落地：`control_tasks + control_task_events`
- [x] main-agent 已成为 parent task 创建者
- [x] Ralph / code-review 已映射为 child task
- [x] control session 第一版落地：`user_session + agent_session + run_session`
- [x] child task 完成/转人工结果已可回写 parent task
- [x] control-plane 查询接口已落地：`/control/tasks/{task_id}` 和 `/control/tasks/{task_id}/events`
- [x] integration diagnostics 第一版落地：`/diagnostics/integrations`
- [x] worker lease / heartbeat / timeout / retry 第一版落地
- [x] Ralph 正式 agent 身份已完成收口：`agent_id / workspace / docs / skills / defaults`
- [x] GitHub issue -> worker claim -> Ralph 编码 -> PR -> review -> repair -> approved 主闭环真实跑通
- [x] `sleep_coding` plan / execution usage 已接入 request ledger
- [x] token ledger `record_request` created_at 插入错误已修复
- [x] MiniMax usage 归一化测试已收敛到仓库默认 `.com` base URL
- [x] token 最终通知已统一为表格化展示
- [x] review usage 已持久化到 `review_runs` 并追加到账本 request 聚合
- [x] task / review / final delivery 已接入统一 `token_usage` 口径
- [x] `/tasks/sleep-coding/{task_id}/actions` 和 `/workers/sleep-coding/poll` 已切到后台 follow-up 模式
- [x] task / control-task / event 已补 `background_follow_up` 可观测状态
- [x] 测试默认静默环境已收口：`app_env=test` 下禁用真实 MCP/webhook 默认副作用
- [x] 服务级 MVP E2E 已补：`main_agent.intake -> worker poll -> review -> final delivery`
- [x] Gateway/Main Agent 主链路已统一 request_id，避免 gateway 包装 main-agent intake 时重复记账
- [x] API 级 MVP smoke 已补：`/gateway/message -> /workers/sleep-coding/poll -> final delivery`
- [x] request 聚合 token 元数据已收口：多 step 聚合时不再错误回填单个 `step_name / provider / model`
- [x] API 级 smoke 已扩到 `gateway / task / review / final delivery` 四个出口的 token 一致性断言
- [x] Feishu inbound 已接上 automation follow-up：`Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`
- [x] `platform.json` 已切到 `sleep_coding.worker.auto_approve_plan=true`，以平台配置作为闭环事实来源
- [x] auto-approve 闭环已抑制 `ready for confirmation` 噪音通知，开始后第二条卡片已改为 `Ralph 执行计划`
- [x] final delivery 通知已补工作总结、Code Review 结果摘要与 token 表，贴近 MVP 产品形态
- [x] final delivery 已继续补齐需求摘要、计划摘要、交付说明与 token 明细指标（缓存/推理/消息数/耗时/总成本）
- [x] final delivery 的 token 外显已从冗长阶段表收口为“总量指标 + 阶段分布摘要”，更贴近飞书卡片阅读
- [x] PR review 回写已升级为结构化“Ralph Review Decision”评论，包含结论、严重级别、关键 findings 与 token 使用
- [x] Main Agent 的 issue prepared 通知已补摘要与 labels，避免飞书只剩 issue 链接
- [x] Ralph 的 PR ready 评论已补来源 issue、分支、计划摘要、验证结果与下一步说明
- [x] sleep-coding review 上下文已补 issue 标题/正文、分支、提交摘要与文件变更，提升 review 输出质量
- [x] Feishu 出站通知已切到 card 模式，保留主链路语义但改善最终外观
- [x] Feishu card 已继续收口为“概览区 + 分段标题 + 结构化列表 + footer”的信息层级
- [x] 文件清单与 token 表在 Feishu card 中已从原始 ASCII 表格改成更适合阅读的结构化列表
- [x] 开始通知与完成通知已切到中文成品语气：`Ralph 任务开始` / `Ralph 任务完成`
- [x] 已基于真实 `.env` 中的 Feishu webhook 发出一轮完整模拟通知，等待用户截图回看样式
- [x] MiniMax token 口径已按官方缓存文档修正：`total input = input_tokens + cache_read_input_tokens + cache_creation_input_tokens`
- [x] pricing 计算已避免对 cache read/write 重复计费
- [x] `GitWorkspaceService` 在显式关闭 `commit/push` 时不再偷偷走 GitHub MCP 写分支
- [x] GitHub 集成已切到 `mcp.json` 配置唯一来源、MCP-only；未配置 GitHub MCP server 时默认失败，不再走 REST fallback 或 `GITHUB_TOKEN` 兜底
- [x] GitHub MCP-only 改造后的 `automation / mvp_e2e / api / full suite` 回归已通过，测试不再依赖 REST fallback 或默认数据库路径偶然成功
- [x] 已完成一轮真实 `MiniMax + Feishu` 安全模拟：`tiezhuli001/youmeng-gateway` / Issue `#101` / 最终 `approved`
- [x] 已完成一轮新的真实 GitHub MCP issue/PR 联调：Issue `#33` -> PR `#35` -> task `a987a809-a08e-409b-8162-0993f4a133fd` -> 最终 `approved`
- [x] 已修复真实 GitHub MCP push 对“新增未跟踪嵌套文件”漏采集的问题；根因是 `git status --short` 折叠目录，现已改为 `--untracked-files=all`
- [x] 已新增回归测试锁住上述真实故障：`tests.test_sleep_coding.GitWorkspaceServiceTests.test_collect_changed_files_includes_untracked_nested_files`
- [x] 已收口正式环境的 LLM 失败语义：真实 provider 已配置但 `main-agent / sleep-coding / review` 调用失败时，不再静默回退 heuristic / dry-run
- [x] `ReviewSkillService` 现在会优先执行显式 `review_skill_command`，不再被环境里的模型凭据抢占
- [x] 测试 helper 已显式隔离本机 `.env` 中的真实模型凭据，避免 `app_env=test` 用例误打外网
- [x] shared LLM runtime 已补统一重试策略：`platform.json` 可配置 `llm.request_timeout_seconds / request_max_attempts / request_retry_base_delay_seconds`，默认按 3 次尝试 + 指数退避执行
- [x] 全量 `python -m unittest discover -s tests -v` 已通过（106 tests）
- [x] 新增会话继承文档：`docs/status/session-handoff.md`
- [x] 文档入口已收口：`docs/README.md` 现在只指向当前 MVP 主事实来源
- [x] `docs/status/backlog.md` 已退出主入口并从当前分支移除，避免继续与 `current-status.md` 形成双事实源
- [x] `docs/review-runs/` 已改为运行时产物目录并从版本控制移出，避免 review artifact 持续放大 PR

## 正在进行

- [x] Phase 0-2 文档与实现对齐
- [x] Phase 3 需求校准：review 由 skill 执行，平台做回写与归档
- [x] Phase 4 需求校准：完成后先做 Phase 0-4 联调
- [x] Phase 3 编码计划归档
- [x] Phase 3 独立 review service / API 第一版落地
- [x] Phase 3 review-runs 运行产物目录落地
- [x] Phase 3 review skill 真正执行链路已接入
- [x] Phase 3 GitLab 评论回写接口已接入
- [x] Phase 4 token ledger 查询 / 报表 API 已完成
- [x] Phase 4 规则化 token 摘要已完成
- [x] 当前实现与目标 MVP 的能力差距已完成梳理
- [x] OpenClaw 架构启发已同步到 MVP 文档
- [x] GitHub MCP 真实环境联调
- [x] review skill 真实环境联调
- [x] Feishu 真实环境联调
- [x] `mcp.json` 配置入口收敛
- [x] agent / skill workspace 文案重写
- [x] `platform.json / agents.json / models.json` 配置入口收敛
- [ ] shared runtime 收敛并替换剩余 service-style agent logic
- [ ] HTTP 长请求的同步/异步行为继续收口，避免“接口看起来挂住但状态已迁移完成”的体验分裂

## 下一步

1. 继续固化围绕 `feishu -> gateway -> issue -> claim -> coding -> review -> final delivery` 的 MVP smoke suite，作为当前阶段主验收口径
2. 继续核对 `feishu / gateway / task / review / final delivery` 五处 token/cost 聚合与展示，确保同一条链路内对外输出一致
3. 继续以 `mcp.json` 为唯一 GitHub/GitLab 配置入口补跑真正的 `issue/PR write` 真实联调，不再补 REST fallback
4. 继续追查 review `real_run` 在本机到 MiniMax 的 TLS/网络问题，避免真实链路在 review 阶段退回 `dry_run`

## 当前阻塞

- 当前本机 `python3` 为 3.14，LangChain 生态有兼容性警告；正式环境应固定在 Python 3.11/3.12
- 主闭环已真实跑通，长请求也已有 `background_follow_up` 可观测状态；当前阶段的主要缺口不再是治理功能数量，而是主链路验收与 token 输出是否稳定
- token ledger 已支持 request 级聚合，`feishu / gateway / task / review / final delivery` 已基本统一到同一口径；gateway 包装 main-agent intake 的重复记账问题已修复，多 step 聚合也不再伪装成单 step 元数据
- Feishu webhook 现在会继续触发 automation follow-up；当前平台默认已经切到自动批准 plan，以保证 MVP 闭环可真实跑通
- auto-approve 模式下，通知链路已从“重复的 awaiting_confirmation”收口为“issue 进入执行 -> final delivery 完成”两段式；当前剩余工作主要是把最终通知内容继续贴近产品预期
- 当前 final delivery 已收口为“总量指标 + 阶段分布摘要”，PR 上也会回写最新 review 决策；主链路剩余问题更偏向内容质量和真实环境联调，而不是闭环缺段
- GitHub/GitLab 外部写操作现在以 `mcp.json` 为唯一主配置入口；若缺少对应 server 或 tool，会显式失败并提示补齐配置，而不是静默退回 REST/env
- issue prepared、PR ready、review decision、final delivery 四段外显现在都已带摘要信息；当前更大的剩余问题是“真实联调环境里这些文案是否已经完全符合产品预期”
- 本轮新的真实 issue/PR 联调已经再次证明 GitHub MCP 写链路可用；当前更突出的剩余风险转为 review LLM 在真实环境下偶发 `SSL: UNEXPECTED_EOF_WHILE_READING`
- 飞书出站已从纯文本切到中文 card 模式，且已补概览区、分段标题和结构化 token 展示；当前剩余问题主要在真实联调里验证“最终成品感”，而不是基础样式能力
- worker 第一版 lease / heartbeat / timeout / retry 已落地；`stuck-task / cancel / resume` 作为运行治理增强项，放在主链路稳定之后
- 当前 agent runtime 已覆盖 main-agent、sleep-coding、review 的核心认知链路，剩余 service 风格逻辑主要在状态机和回写编排层
- LLM 请求层此前只有 timeout，没有统一 retry；现已补到 shared runtime，避免偶发网络/TLS 抖动直接打穿主链路
- 文档层此前同时混有当前事实、历史 phase 计划、未来方向预研和 review 运行产物；现已开始按“当前入口 / 运行时产物”收口，并把历史/中间方案直接从当前分支剥离
- daily token summary 已具备生成入口，但“每日 10 点”真实调度仍待联调环境验证

## 当前技术决定

- 第一阶段不直接做 `Feishu -> OpenClaw -> OpenCode 自动编码`
- 第一阶段先做：
  - 文档体系
  - 环境体系
  - 平台骨架
  - 最小意图路由与状态读取
- Phase 2 先做单任务、单仓库、人工确认的睡后编程 MVP
- Phase 2 允许向 Channel 发送出站通知，但不在飞书内做审批闭环
- Ralph 作为正式 agent 身份，默认通过 `agent:ralph` 标签与 `agents/ralph` workspace 体现；`workflow:sleep-coding` 仅表示流程类型
- Phase 3 采用 skill 驱动 review，平台只做最小状态、归档、回写和流转
- `code review agent` 是独立能力，sleep coding 只是其触发来源之一
- `docs/code-review/` 与 `docs/review-runs/` 目录职责分离
- 第一阶段真正的需求验证节点放在 Phase 4 结束后统一执行
- 后续编码以 Phase 文档为唯一阶段基线，先补文档再补实现
- 数据层策略为：`Phase 1 / Phase 2` 先 SQLite，后续再迁移 PostgreSQL
- Phase 4 的 token ledger 采用确定性工程实现，规则摘要不依赖 skill 或 LLM
- 进入 MVP 收口阶段后，issue 理解、计划、编码、review、repair 等认知工作优先交给 LLM + skill + MCP
- Feishu 鉴权、token 账本、调度、幂等、状态机等基础设施继续保持工程化实现
- MVP 文档方向已修正为 OpenClaw 风格：Gateway 作为控制平面，Shared Runtime 复用 provider / skill / MCP，Agent 只保留角色与边界
- 当前 shared runtime 的最小边界已明确为：`llm`、`skills`、`mcp`、`agent_runtime`
- Main Agent 与 Ralph 的核心认知链路已开始按 workspace + skill + MCP 的方式表达能力，而不是继续增加 if/else 逻辑
- review 运行产物默认仍写入 `docs/review-runs/`，但该目录现在只作为本地运行时目录，不再作为仓库内长期事实源

## 当前事实来源

本文件是当前阶段状态的主事实来源。OpenClaw 后续应优先读取本文件回答：

- 当前做到哪了？
- 现在在做什么？
- 下一步做什么？
