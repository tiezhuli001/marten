# Current Status

> 更新时间：2026-03-19
> 当前阶段：已进入能力内聚阶段，`Round Next-C` 收尾验证已完成
> 当前目标：在 `channel -> control plane -> runtime -> agent` 的极简骨架上继续压缩可压缩复杂度，并保持 agent spec / control event / short-memory facade 为稳定边界，同时补齐真实链路验收

## 当前结论

- 主仓库已经确定：`youmeng-gateway`
- 开发主环境确定为：Linux 服务器
- 当前交互模式确定为：
  - `OpenClaw`: 沟通、进度反馈、飞书入口
  - `OpenCode`: 服务器上的交互式编码助手
  - `Gateway Control Plane + Shared Runtime + LangSmith`: 当前编排与观测方案

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
- [x] `/gateway/message` 已退出 `LangGraph WorkflowRunner` 主入口，改由 `GatewayControlPlaneService` 承接 control plane 编排
- [x] 已新增轻量 control 目录：`app/control/gateway.py / routing.py / events.py`
- [x] automation follow-up 已从直接 threadpool 回调收口到 `ControlEventBus`
- [x] `app/graph/*` 已从当前主路径移除并删除，避免继续形成双编排中心
- [x] 旧的 4 轮架构收敛计划已完成并退出文档主入口，当前由 `docs/plans/capability-gap-and-optimization-plan.md` 继续承接
- [x] Round 2 第一版 agent application modules 已落地：`app/agents/main_agent / ralph / code_review_agent`
- [x] control plane / API / automation / worker 的主路径 import 已切到 `app/agents/*`
- [x] `app/services/main_agent.py / sleep_coding.py / review.py` 已降为兼容壳层，避免一次性迁移破坏测试与调用方
- [x] Round 3 第一版 context assembly / short-memory boundary 已落地：`app/control/context.py`
- [x] `control_sessions.payload` 已支持 short memory summary 挂载；session registry 已补 payload update / ancestry chain 查询
- [x] main-agent / ralph / code-review-agent 已开始统一通过 context assembly 读写 short memory
- [x] 全量 `python -m unittest discover -s tests -v` 已通过（110 tests）
- [x] Round 4 第一版 infra / channel 边界收敛已落地：`app/channel/*` 与 `app/infra/*`
- [x] `app/main.py`、`app/api/routes.py`、`app/services/automation.py`、agent 主路径 imports 已切到 `channel/infra` 边界
- [x] `app/services/channel.py / feishu.py / background_jobs.py / scheduler.py / diagnostics.py / git_workspace.py` 已降为兼容 facade
- [x] `app/channel/__init__.py / app/control/__init__.py / app/infra/__init__.py` 已改为最小入口，避免 package eager import 放大循环依赖
- [x] Round 4 高相关回归已通过：`test_channel / test_feishu / test_scheduler / test_automation / test_api / test_mvp_e2e / test_control_context / test_session_registry / test_router`
- [x] Round 4 全量 `python -m unittest discover -s tests -v` 已通过（110 tests, 129.891s）
- [x] 真实配置诊断已通过：`github_mcp=ok`、`review_skill=runtime_llm`、`feishu=inbound/outbound ok`
- [x] 已完成一轮安全近真实全链路模拟：`Feishu signature -> gateway -> main-agent -> worker poll -> Ralph -> review -> notification`
- [x] 近真实全链路模拟在关闭真实 LLM 出口后已跑通，结果为：Issue 创建成功、3 条通知发出、claim 最终 `failed`（失败点为 validation）
- [x] 能力差异与优化清单计划已归档：`docs/plans/capability-gap-and-optimization-plan.md`
- [x] 下一轮收敛顺序已明确：先压 `Ralph / Review Agent / Worker` 三个复杂度黑洞，再收 agent spec，再收 event/memory 边界
- [x] `Round Next-A` 第一版已完成：Ralph drafting / GitHub bridge 已拆出 helper modules
- [x] `Round Next-A` 第一版已完成：Review Agent store / source support 已拆出 helper modules
- [x] `Round Next-A` 第一版已完成：worker 实现已迁到 `app/control/sleep_coding_worker.py`
- [x] 已删除已完成且形成双事实源的旧计划文档：`mvp-architecture-convergence-plan.md`、`mvp-multi-round-execution-plan.md`
- [x] `Round Next-A` 完成后全量测试仍通过：`110 tests OK`
- [x] `Round Next-A` 第二版已完成：Ralph task persistence/store 已拆到 `app/agents/ralph/store.py`
- [x] `Round Next-A` 第二版已完成：Review comment writeback / context assembly 已拆到 `app/agents/code_review_agent/bridge.py` 与 `context.py`
- [x] `Round Next-A` 第二版已完成：worker claim store 已拆到 `app/control/sleep_coding_worker_store.py`
- [x] 复杂度黑洞厚度进一步下降：`ralph/application.py 1293 -> 995`、`review/application.py 902 -> 779`、`worker 735 -> 504`
- [x] `Round Next-A` 第二版回归已通过：高相关 `60 tests OK`，全量 `110 tests OK`
- [x] `Round Next-B` 第一版已完成：`AgentSpec` 与 `Settings.resolve_agent_spec(agent_id)` 已落地
- [x] `Round Next-B` 第一版已完成：`AgentDescriptor.from_spec(...)` 已成为 agent descriptor 主路径
- [x] `Round Next-B` 第一版已完成：runtime workspace instructions 已正式纳入 `SOUL.md`
- [x] `Round Next-B` 第一版已完成：`agents.json` 已补 `system_instruction / memory_policy / execution_policy`
- [x] `Round Next-B` 第一版已完成：三个 agent workspace 已补 `SOUL.md`
- [x] `Round Next-B` 第一版回归已通过：高相关 `67 tests OK`，全量 `111 tests OK`
- [x] `Round Next-C` 第一版已完成：control event 已开始显式化为 domain events，并保持 legacy event 兼容
- [x] `Round Next-C` 第一版已完成：short memory 已从单一 summary 挂点升级为 `append/list` facade
- [x] `Round Next-C` 第一版回归已通过：高相关 `44 tests OK`，全量 `112 tests OK`
- [x] `Round Next-C` 收尾压缩已完成：`app/services/automation.py` 已从 `528 -> 280`
- [x] `Round Next-C` 收尾压缩已完成：follow-up 控制已拆到 `app/control/follow_up.py`
- [x] `Round Next-C` 收尾压缩已完成：交付文案组装已拆到 `app/channel/delivery.py`
- [x] `Round Next-C` 收尾压缩回归已通过：高相关 `39 tests OK`，全量 `112 tests OK`
- [x] 真实 Feishu 出站验证已补：webhook 实发成功，`delivered=True`
- [x] GitHub 实链路核验已补：真实 issue/PR 已创建，最新验证样本为 `issue #45` / `PR #46`
- [x] 全量回归已再次通过：`python -m unittest discover -s tests`，`114 tests OK`

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
- [x] MVP 第一轮结构收敛：gateway control plane / event bus / graph cleanup
- [x] MVP 第二轮第一版收敛：agent application modules 显式化
- [x] MVP 第三轮第一版收敛：context assembly / 短记忆边界
- [x] MVP 第四轮第一版收敛：infra / channel 边界显式化与兼容壳层压缩
- [x] 下一轮复杂度压缩计划已成文，并已纳入文档入口
- [x] `Round Next-A` 第一版复杂度压缩已落地
- [ ] HTTP 长请求的同步/异步行为继续收口，避免“接口看起来挂住但状态已迁移完成”的体验分裂
- [ ] 真实 MiniMax 链路的 `SSL: UNEXPECTED_EOF_WHILE_READING` 需要继续定位
- [x] Round Next-A 第二版：继续拆薄 `Ralph / Review Agent / Worker`
- [x] Round Next-B：收口 declarative agent spec
- [x] Round Next-C：收口 control event / memory boundary
- [x] 下一轮复杂度压缩第一版已完成：`automation` 主编排已显著收薄
- [x] 真实 Feishu / GitHub MCP 验收已补：主链路稳定跑到 `PR Ready`
- [ ] 继续压缩剩余厚 application 文件，避免 domain event / memory facade 再回流
- [ ] 真实 review / final delivery 的全外部系统闭环仍需继续压测，避免重复 issue/PR 验证样本累积

## 下一步

1. 继续压缩 `Ralph / Review Agent` 剩余厚文件，保持 `Automation / FollowUp / Delivery` 的新边界不回流
2. 补真实 review / final delivery 的外部系统闭环验收，避免全链路只稳定在 `PR Ready`
3. 编码前持续检查是否仍符合 `channel -> control plane -> runtime -> agent`
4. 编码后跑测试，再更新 `current-status.md` 和 `session-handoff.md`
5. 保持 `agents.json -> resolve_agent_spec -> AgentDescriptor.from_spec -> runtime prompt` 为单一事实源
6. 在结构继续稳定后，再回到真实 MiniMax `SSL EOF` 问题

## 当前阻塞

- 当前本机 `python3` 为 3.14，LangChain 生态有兼容性警告；正式环境应固定在 Python 3.11/3.12
- 当前真实 MiniMax 调用在本机近真实回测里出现 `SSL: UNEXPECTED_EOF_WHILE_READING`；控制面与模拟外部系统链路正常，阻塞点集中在 provider 传输层
- 真实 Feishu 出站已经确认可用，GitHub MCP issue/PR 写链路也再次确认可用；当前真实外部链路剩余不稳定点主要在 review/final delivery 收尾与 MiniMax 传输层
- 主闭环已真实跑通，长请求也已有 `background_follow_up` 可观测状态；当前阶段的主要缺口不再是治理功能数量，而是主链路验收与 token 输出是否稳定
- `gateway` 主入口已收口到 control plane，agent application modules 与 context assembly 也已显式化；当前剩余缺口转为 infra 边界与兼容壳层压缩
- Round 4 已把 `channel/infra` 目录边界立起来，当前 `services/*` 中剩余的大多是兼容 facade 或仍承载领域服务的稳定模块，不应再做无收益迁移
- 新增能力差异文档后，当前收敛顺序已经明确：先压厚文件和 worker 边界，再收 declarative agent spec，再补 event/memory；不应跳步骤并行重构
- `Round Next-A`、`Round Next-B`、`Round Next-C` 已完成第一版；agent spec、control event、short-memory facade 都已立起稳定边界，`automation` 也已显著收薄，当前主要剩余厚度集中在 `Ralph / Review Agent`
- token ledger 已支持 request 级聚合，`feishu / gateway / task / review / final delivery` 已基本统一到同一口径；gateway 包装 main-agent intake 的重复记账问题已修复，多 step 聚合也不再伪装成单 step 元数据
- Feishu webhook 现在会继续触发 automation follow-up；当前平台默认已经切到自动批准 plan，以保证 MVP 闭环可真实跑通
- auto-approve 模式下，通知链路已从“重复的 awaiting_confirmation”收口为“issue 进入执行 -> final delivery 完成”两段式；当前剩余工作主要是把最终通知内容继续贴近产品预期
- 当前 final delivery 已收口为“总量指标 + 阶段分布摘要”，PR 上也会回写最新 review 决策；主链路剩余问题更偏向内容质量和真实环境联调，而不是闭环缺段
- GitHub/GitLab 外部写操作现在以 `mcp.json` 为唯一主配置入口；若缺少对应 server 或 tool，会显式失败并提示补齐配置，而不是静默退回 REST/env
- issue prepared、PR ready、review decision、final delivery 四段外显现在都已带摘要信息；当前更大的剩余问题是“真实联调环境里这些文案是否已经完全符合产品预期”
- 本轮新的真实 issue/PR 联调已经再次证明 GitHub MCP 写链路可用；当前更突出的剩余风险转为 review LLM 在真实环境下偶发 `SSL: UNEXPECTED_EOF_WHILE_READING`
- 本轮已新增一条真实 Feishu webhook 出站验证消息；如果用户飞书侧已看到 `Youmeng Gateway 全链路验证` 卡片，说明当前 webhook 出站链路可用
- 真实 GitHub 外部样本已推进到 `issue #45 -> PR #46`，且 issue 评论已出现 `Ralph PR Ready` 回写；当前更大的剩余问题不是写链路，而是避免重复验证时不断堆积 issue/PR 样本
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
- 当前代码主入口已进一步向 `nanobot/OpenClaw` 风格收口：`channel -> control plane -> runtime -> agent`
- agent 代码结构已开始与运行时/控制平面解耦：`app/agents/*` 成为显式应用层入口，`app/services/*` 暂时保留兼容 facade
- 当前短记忆策略确定为：先把 summary 挂在 `control_sessions.payload`，通过 `ContextAssemblyService` 统一读写；长记忆接口后置，不在当前阶段前置复杂检索
- 当前 infra / channel 策略确定为：主路径直接依赖 `app/channel/*` 与 `app/infra/*`，`app/services/*` 只保留仍有调用价值的领域服务与过渡 facade
- 当前 `Round Next-A` 策略已完成：通过 helper/module/store 抽离压缩厚文件，且没有改变 `SleepCodingService / ReviewService / WorkerService` 对外接口
- 当前 `Round Next-B` 策略已完成：继续保持主链路不变，已收口 agent spec 与 workspace docs 驱动能力，没有引入新的平台层
- 当前 `Round Next-C` 策略确定为：优先显式化 domain events 与 short-memory facade，不做 RAG、向量库或 MQ 扩张
- 当前 shared runtime 的最小边界已明确为：`llm`、`skills`、`mcp`、`agent_runtime`
- Main Agent 与 Ralph 的核心认知链路已开始按 workspace + skill + MCP 的方式表达能力，而不是继续增加 if/else 逻辑
- review 运行产物默认仍写入 `docs/review-runs/`，但该目录现在只作为本地运行时目录，不再作为仓库内长期事实源

## 当前事实来源

本文件是当前阶段状态的主事实来源。OpenClaw 后续应优先读取本文件回答：

- 当前做到哪了？
- 现在在做什么？
- 下一步做什么？
