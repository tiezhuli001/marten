# Session Handoff

> 更新时间：2026-03-18
> 用途：为新会话提供可直接继承的背景，避免从零重新阅读整个仓库和历史对话。

## 当前目标

当前目标没有偏移，仍然是：

- 维持三 Agent 主闭环：`main-agent`、`ralph`、`code-review-agent`
- 维持 JSON-first 配置：`agents.json / models.json / platform.json / mcp.json`
- 在真实环境下把 issue -> claim -> coding -> PR -> review -> repair -> notify 做稳
- 在此基础上优先收口 token/cost 展示与主链路验收；运行治理增强项暂不前置扩展
- GitHub/GitLab 外部能力继续坚持配置优先：`mcp.json` 已配置才可执行，未配置默认失败，不再走 REST fallback

## 已完成的关键事实

- 主闭环已真实跑通，不只是 dry-run
- GitHub MCP、review、Feishu 均已有真实联调样本
- `sleep_coding` 的 claim 同步、repair round 复用既有 PR、最终 approved 闭环都已验证过
- `platform.json` 仍是平台级配置事实来源，没有改成环境变量覆盖平台默认

## 本轮已完成

- 做了一轮新的真实 GitHub MCP 主链路联调：
  - 真实 issue：`#33`
  - 真实 PR：`#35`
  - 真实分支：`codex/issue-33-sleep-coding`
  - 本地临时联调库：`/var/folders/m_/nb1l2kr97tg2xn6bn40yy69m0000gn/T/youmeng-live-20260318-200105-9cwfe_0w/live.db`
  - 最终 task：`a987a809-a08e-409b-8162-0993f4a133fd`
  - 最终状态：`approved`
  - 本轮 task 总 token：`2162`（`prompt=1035`，`completion=1127`）
- 真实联调暴露并修复了 GitHub MCP push 的主链路缺陷：
  - 问题现象：issue `#33` 首轮执行后远端分支已创建，但 `create_pull_request` 返回 `No commits between main and codex/issue-33-sleep-coding`
  - 根因：`GitWorkspaceService._collect_changed_files()` 使用 `git status --short`，会把未跟踪目录折叠成目录项，例如 `docs/e2e/`，导致新增文件被跳过，`push_files` 实际没有把新文件推到 GitHub
  - 修复：改为 `git status --short --untracked-files=all`
  - 新增回归：`tests.test_sleep_coding.GitWorkspaceServiceTests.test_collect_changed_files_includes_untracked_nested_files`
- 修复后已确认：
  - 远端分支 diff 存在：`.sleep_coding/issue-33.md`、`docs/e2e/issue-33.md`
  - issue `#33` 已有 `Ralph PR Ready` 评论
  - PR `#35` 已存在 review 记录
  - 本地 task 已从 `awaiting_confirmation` 走到 `approved`
- 本轮也确认了一个剩余真实风险：
  - 这次 review 不是 `real_run`，而是 fallback 到 `dry_run`
  - 直接复现 `ReviewSkillService._run_with_agent_runtime()` 时，真实异常为：
    - `RuntimeError: LLM provider is unreachable: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol`
  - 说明当前 review fallback 不是配置缺失，而是本机到 MiniMax 的真实 TLS/网络可达性问题
- 继续收口了“正式环境显式失败、测试环境可控回退”的边界：
  - `MainAgentService` 在真实 provider 已配置但 issue draft LLM 调用失败时，不再静默回退 heuristic issue；正式环境会直接报错
  - `SleepCodingService` 在真实 provider 已配置但 plan / execution LLM 调用失败时，不再静默回退 heuristic plan/execution；正式环境会直接报错
  - `ReviewSkillService` 在配置了显式 `review_skill_command` 时，会优先执行 command，而不是被环境里的模型凭据抢走
  - `ReviewSkillService` 在正式环境 LLM review 失败时，不再偷偷回退 `dry_run`
  - `app_env=test` 下仍保留可控回退，避免单测误打真实网络
- 收口了测试环境对本机 `.env` 的污染：
  - `tests.test_main_agent / tests.test_review / tests.test_automation / tests.test_mvp_e2e` 的 settings helper 现在会显式把 `openai_api_key / minimax_api_key` 置空
  - 避免测试因为本机真实 MiniMax 凭据而误走外网

- 将 GitHub 外部操作继续收口到 MCP-only：
  - `MainAgentService` 创建 issue 不再走 REST fallback
  - `SleepCodingService` 的 `get_issue / issue_comment / apply_labels / create_pull_request` 不再走 REST fallback
  - `ReviewService` 的 PR review 回写不再走 REST fallback
  - `SleepCodingWorkerService` issue discovery 不再走 REST fallback
  - 缺少 GitHub MCP server 或 required tool 时，会显式报错要求补齐 `mcp.json`
- `load_mcp_server_definitions()` 已改为只从 `mcp.json` 加载 server 定义，不再自动拼 legacy env GitHub server
- `GitWorkspaceService` 的 PAT 解析已调整为只读 `mcp.json`，不再回退 `GITHUB_TOKEN`
- 测试已开始同步到显式 MCP 注入：
  - `tests.test_main_agent / tests.test_sleep_coding / tests.test_sleep_coding_worker / tests.test_review / tests.test_runtime_components` 已完成
  - 本轮继续在 `tests.test_automation / tests.test_mvp_e2e / tests.test_api` 上收口
- 收口了测试缓存与默认数据库路径问题：
  - `tests.test_api` 现在会显式清理 `get_settings()` 和路由级单例缓存
  - `tests.test_mvp_e2e` 现在会显式注入临时 `DATABASE_URL / REVIEW_RUNS_DIR / PLATFORM_CONFIG_PATH`
  - 避免局部跑测试时误吃默认 SQLite 路径，导致“全量能过、子集失败”的噪音
- 本轮验证通过：
  - `python -m unittest -v tests.test_automation tests.test_mvp_e2e tests.test_api`
  - `python -m unittest discover -s tests -v`
  - 全量通过：`103 tests / OK`

- 收口了飞书通知的第二条消息语义：
  - `sleep_coding.start_task()` 不再发无信息量的 `PR ready for Issue`
  - 现在会发送 `Ralph 执行计划：...`
  - 内容包含 `来源 / 仓库 / 分支 / Issue / 计划摘要 / 执行计划(1..N)`
  - worker / gateway auto-approve 路径也会保留这张计划卡，不再因为自动批准而缺失 plan 外显
- 收口了 final delivery 的 token 外显：
  - 不再把阶段表和指标表整块堆进飞书卡片
  - 现在改成 `总量指标 + 阶段分布摘要`
  - 总量保留 `输入 / 输出 / 总 Token / 缓存读写 / 推理 / 消息数 / 耗时 / 总成本`
- 修正了 MiniMax token/cost 口径：
  - `SharedLLMRuntime._build_usage()` 现在按官方文档把 `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` 视为总输入
  - `PricingRegistry.calculate_cost_usd()` 现在会从 `prompt_tokens` 中扣除 cache read/write，再计算基础 input cost，避免重复计费
  - 新增回归测试覆盖 MiniMax cache usage 聚合与计费
- 修正了安全模拟路径的 GitHub MCP 写分支问题：
  - `GitWorkspaceService` 只有在 `enable_git_commit=true && enable_git_push=true` 时才允许走 GitHub MCP 写路径
  - 显式关闭 `commit/push` 的真实联调不会再误触发 MCP push
- 完成了一轮真实 `MiniMax + Feishu` 的安全联调模拟：
  - 目标仓库仍为 `tiezhuli001/youmeng-gateway`
  - 采用临时 `platform.json` 显式关闭 `commit/push`
  - 使用真实 `MiniMax API` 生成 plan / execution / review
  - 使用真实 `Feishu webhook` 发出计划卡与完成卡
  - 最终结果：`approved`
  - compare 链接：`https://github.com/tiezhuli001/youmeng-gateway/compare/main...codex/issue-101-sleep-coding`
  - 本轮 ledger 聚合：`prompt_tokens=694`，`completion_tokens=730`，`total_tokens=1424`，`cost_usd=0.001084`
- 明确了当前环境的真实阻塞：
  - 截至 `2026-03-18`，当前环境 `GITHUB_TOKEN=false`
  - 同时 `mcp_github_enabled=false`
  - 所以“真实写 GitHub issue/PR”仍受凭据阻塞；当前已先把 `MiniMax + Feishu + 产品通知链路` 做到真实联调

- 将开始/完成通知的标题语气继续收口到更贴近产品的中文表达：
  - `MainAgentService` 的开始通知现在是 `Ralph 任务开始：...`
  - `AutomationService` 的结束通知现在是 `Ralph 任务完成：...`
  - `gateway -> main-agent` 路径下会复用开始通知，不再额外发送一张重复的 `Started Issue` 卡片
- 将开始通知内容继续对齐产品预期：
  - 开始卡现在会展示 `来源 / 仓库 / 创建人 / 状态|标签 / Issue / 任务摘要`
  - 并以 `Ralph 正在处理中，完成后将自动提交 Pull Request...` 收尾
- 将完成通知内容继续对齐产品预期：
  - 顶部展示 `来源 / 仓库 / 分支 / Pull Request or Merge Request / Code Review / Issue / Review`
  - `工作总结` 下面按 `修改文件清单 -> 关键变更说明 -> Token 消耗统计 -> 总结` 编排
  - 完成卡结尾会明确写出 `Ralph 已完成任务，请过目。`
- 使用真实 `.env` 中配置的 `CHANNEL_WEBHOOK_URL` 发出了一轮完整模拟通知：
  - 使用真实 Feishu webhook 出站
  - GitHub / review / git workspace 仍使用本地测试桩，避免污染真实仓库
  - 当前已可以等待用户返回飞书截图，继续按真实视觉效果微调
- 继续收口 Feishu card 的信息编排，而不改变主链路状态语义：
  - card 现在有更明确的 `概览区`
  - section 之间会插入分隔
  - 卡片底部会带统一 footer：`Youmeng Gateway · Sleep Coding MVP`
- 继续收口卡片里的表格展示：
  - `修改文件清单` 不再原样显示 ASCII 表格
  - `Token 消耗统计` 也不再原样显示 ASCII 表格
  - 两者都会在 card 中转成更适合阅读的结构化列表项
  - 这样飞书里的文件清单和 token 区域已经比上一轮更像成品，而不是控制台输出截图
- 新增一条 card 编排回归：
  - `tests.test_channel.ChannelNotificationServiceTests.test_feishu_card_renders_file_table_as_list_items`
  - 用来锁住文件清单不会退回原始文本表格
- 将 Feishu 出站通知从纯文本收口到 card 模式：
  - `ChannelNotificationService` 对 `provider=feishu` 现在发送 `interactive card`
  - 按标题语义自动选择 header 颜色：
    - `任务完成` -> `green`
    - `Started Issue` -> `orange`
    - `Manual review required / failed` -> `red`
    - 其他 -> `blue`
  - 普通 `key: value` 行会转成更适合卡片阅读的 markdown
  - URL 会自动转成可点击链接
  - 表格段会保留为独立 block，避免和正文混在一起
  - 这次只优化飞书呈现层，没有改主链路状态语义
- 新增 `tests/test_channel.py`，把 Feishu card payload 锁进回归：
  - 断言 `msg_type=interactive`
  - 断言 header template 会随 `Started Issue / 任务完成` 变化
  - 断言链接与表格 block 不会退回纯文本拼接
- 继续收口 `issue prepared` 这一段通知，避免主链路一开始就像半成品：
  - `MainAgentService` 的 `GitHub issue prepared` 通知现在会带 `Summary` 与 `Labels`
  - 飞书里不再只有 repo/title/url 三行
- 继续收口 `PR ready` 这一段外显：
  - Ralph 在 issue 评论里写入的 `Ralph PR Ready` 现在会带 `来源 Issue / Branch / Plan Summary / Validation / 下一步`
  - 这样在 PR/review 开始前，用户已经能看到“ralph 开始怎么做、当前做到了哪”
- 继续提升 review 输入质量：
  - `ReviewService._build_context()` 现在会为 sleep-coding task 补 `Issue Title / Issue Body / Head Branch / Commit Summary / File Changes`
  - review skill 拿到的上下文不再只有 task id / repo / artifact / plan
  - 这会直接影响后续 review 输出质量与最终通知摘要质量
- 继续收口 final delivery 的产品外显：
  - `工作总结` 现在会补 `需求摘要`、`计划摘要`、`提交摘要`
  - 新增 `四、交付说明`
  - 会明确提示当前 MVP 口径为“Ralph 已完成编码与评审闭环，请人工合并 PR”
- 继续收口 token 外显：
  - final delivery 在原有 `Plan / Execution / Review / Total` 阶段表之外
  - 新增总量指标表：`缓存读取 Token / 缓存写入 Token / 推理 Token / 消息数量 / 处理时间 / 总成本`
  - 这样飞书最终通知已经更接近产品预期里的 token 展示形态
- 收口 PR review 回写：
  - review `approve_review / request_changes` 不再只写简短 summary
  - 现在会回写结构化 `Ralph Review Decision` 评论
  - 评论中包含 `Decision / Blocking / Summary / Severity / Findings / Token Usage`
  - 这样 PR 页面可以看到最新一次 review 决策结果，而不是只有初始 review markdown
- 收口了 auto-approve 模式下的通知语义，避免 Feishu 群里重复刷 `awaiting_confirmation`：
  - `SleepCodingTaskRequest` 新增 `notify_plan_ready`
  - direct gateway / worker auto-approve 路径会显式关闭 plan-ready 通知
  - 自动闭环模式下不再发送 `[Ralph] Issue #... ready for confirmation`
- 新增执行开始通知，补上 “Ralph 已开始处理 issue” 这一段产品链路：
  - `approve_plan` 进入首次执行时，会发送 `[Ralph] Started Issue #...`
  - 通知会带 repo / task / branch / issue / plan
  - `coding_draft_generated` 事件 payload 也会持久化 `artifact_path / file_changes`
- 收口 final delivery 通知内容，贴近 MVP 目标中的“睡后编程产品”外显：
  - 标题改为 `[Ralph] 任务完成：...`
  - 头部显式展示 `来源 / 仓库 / 分支 / Task / 状态 / Issue / PR / Review`
  - 新增 `工作总结`
  - 新增 `一、修改文件清单`
  - 新增 `二、Code Review 结果`
  - 保留 `三、Token 消耗统计`
  - 如果当前轮没有结构化 `file_changes`，会回退展示 artifact 路径，避免最终通知出现空白摘要
- 打通了 Feishu inbound 的完整 follow-up 主链路：
  - `FeishuWebhookService` 不再只调用 `WorkflowRunner`
  - webhook 现在会继续调用 `AutomationService`
  - `general` 意图会触发 `worker poll`
  - `sleep_coding` 意图如果拿到 `task_id`，会继续走 `approve_plan`
  - ack 响应会带 `automation_follow_up`，用于观测 webhook 是否已继续推进
- `GatewayMessageResponse` 现在会显式返回 `task_id`，便于 Feishu 和后续 API 继续推进同一条任务链
- 将平台级事实来源 `platform.json / platform.json.example` 的 `sleep_coding.worker.auto_approve_plan` 调整为 `true`：
  - 不走环境变量覆盖
  - 继续保持 `platform.json` 作为平台行为事实来源
  - 这样 Feishu inbound 和 gateway 主链路默认都能进到完整闭环，不再停在 `awaiting_confirmation`
- 新增一条更贴近真实配置的 Feishu E2E smoke：
  - `Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`
  - 覆盖 webhook 验签、gateway、worker follow-up、review、final delivery
  - 断言 final delivery 通知已发出，task 最终为 `approved`
- 修复了 request 聚合 token 元数据的误导性输出：
  - `TokenLedgerService.get_request_usage()` 在聚合多个 step 时，不再用 `MAX(step_name/provider/model)` 回填总量结果
  - 现在只有单一 `step_name / provider / model` 时才保留该元数据；否则返回 `null`
  - 这样 `task.token_usage` 的总量视图不会再错误显示成某一个单步，例如 `sleep_coding_plan`
- 扩展了 API 级主链路 smoke，覆盖四个 token 出口：
  - `gateway response.token_usage`
  - `GET /tasks/sleep-coding/{task_id}` 的 `task.token_usage`
  - `GET /reviews/{review_id}` 的 `review.token_usage`
  - final delivery 通知中的 `Plan / Execution / Review / Total` 表格
  - 断言 task 总量 `step_name == null`，review 单步仍为 `code_review`
- 修复了 `gateway -> main-agent intake` 的 request ledger 重复记账问题：
  - `MainAgentIntakeRequest` 现在支持透传 `request_id / run_id`
  - `WorkflowRunner` 在 `general_handler` 中会把 gateway request 透传给 `MainAgentService.intake()`
  - `MainAgentService.intake()` 新增 `persist_usage` 开关；被 gateway 包装调用时只复用同一个 request_id，不再二次 `record_request`
  - `sleep_coding` worker 现在会继续沿用同一个主链路 request_id 做 plan / execution / review 聚合
- 新增一条更贴近真实配置的 API 级 MVP smoke：
  - `/gateway/message -> /workers/sleep-coding/poll -> final delivery`
  - 使用真实 `WorkflowRunner / MainAgentService / SleepCodingService / SleepCodingWorkerService / ReviewService / AutomationService`
  - 仅替换 GitHub / review skill / channel / git workspace / validation 为测试桩
  - 断言 `task.kickoff_request_id == gateway.request_id`
  - 断言 final delivery 表格中的 `Plan / Execution / Review / Total` 数值与 ledger 聚合一致
- 全量回归口径已更新：
  - `python -m unittest discover -s tests -v`
  - 当前为 `100` tests / `OK`
- 重新核对了 `docs/plans/mvp-execution-plan.md` 与 `docs/requirements/mvp-gap-analysis.md`：
  - 当前 MVP 主目标仍然是 `gateway -> issue -> claim -> coding -> review -> final delivery`
  - token/cost 计算与最终输出属于当前主目标的一部分
  - `stuck-task / cancel / resume / manual handoff` 属于运行治理增强项，不是当前主验收阻塞项
- 按主链路口径补跑了一组聚焦 smoke：
  - `tests.test_mvp_e2e`
  - `tests.test_automation.AutomationServiceTests.test_auto_review_approves_clean_pr_and_sends_final_delivery`
  - `tests.test_api.ApiTests.test_gateway_message_endpoint`
  - `tests.test_api.ApiTests.test_main_agent_intake_endpoint`
  - `tests.test_api.ApiTests.test_sleep_coding_worker_poll_endpoint`
  - `tests.test_sleep_coding.SleepCodingServiceTests.test_start_and_approve_plan_append_usage_to_kickoff_request`
  - `tests.test_review.ReviewServiceTests.test_trigger_for_sleep_coding_task_and_request_changes`
- 上述主链路 smoke 当前已通过，说明现阶段应继续围绕主链路和 token 输出收口，而不是继续扩治理面
- 为 `task` 补了显式的后台 follow-up 可观测状态：
  - `SleepCodingTask` 新增 `background_follow_up_status` / `background_follow_up_error`
  - `sleep_coding_tasks` 表已持久化该状态
  - task events 现在会记录 `background_follow_up_queued / processing / completed / failed`
- 为 `control-task` 也补了对应可观测状态：
  - control task payload 会回填 `background_follow_up_status` / `background_follow_up_error`
  - control task events 会记录 `background_follow_up_*`
  - parent task 会收到 `child_background_follow_up_*` 事件
- 为长请求补了明确的后台 follow-up 边界：
  - `app/services/background_jobs.py` 新增最小后台执行器
  - `AutomationService.handle_sleep_coding_action_async()` 现在只做前台状态推进，review/repair follow-up 改为后台继续
  - `AutomationService.process_worker_poll_async()` 现在只返回本轮 poll 结果，后续 `in_review / changes_requested` task 改为后台继续
  - `/tasks/sleep-coding/{task_id}/actions` 与 `/workers/sleep-coding/poll` 已切到 async follow-up 版本
  - `WorkerSchedulerService` 也改为触发 async poll，而不是在调度线程里同步跑完整闭环
- 收口了测试环境噪音：
  - `app/runtime/mcp.py` 在 `app_env=test` 下默认不加载真实 MCP adapter
  - `app/services/channel.py` 在 `app_env=test` 下默认不走真实 webhook 出站
  - `tests/test_api.py` 现在会在导入应用前显式设置 `APP_ENV=test` 与临时数据库/产物目录
  - 各测试 helper 的 `Settings(...)` 已统一补 `app_env=\"test\"`
  - 修复 `FeishuWebhookService` 的 `url_verification` 校验顺序，避免 challenge 请求被消息签名分支误拦截
- 新增/更新回归测试，覆盖：
  - async action 只排队 follow-up、不阻塞当前请求
  - async worker poll 只返回当前 poll 结果、把后续处理交给后台
  - background follow-up 状态会回写到 task/control-task/event
  - 新增一条服务级 MVP E2E：`main_agent.intake -> worker poll -> review -> final delivery`
  - API 测试在默认命令下可直接通过，不再依赖手工注入临时环境变量

## 本轮验证

- 新增通过：
  - `python -m unittest -v tests.test_sleep_coding.GitWorkspaceServiceTests.test_collect_changed_files_includes_untracked_nested_files`
  - `python -m unittest -v tests.test_sleep_coding.GitWorkspaceServiceTests.test_dry_run_worktree_commit_push`
  - `python -m unittest -v tests.test_main_agent tests.test_sleep_coding tests.test_review`
  - `python -m unittest -v tests.test_automation`
  - `python -m unittest -v tests.test_mvp_e2e`
  - `python -m unittest discover -s tests -v`
  - 真实 GitHub MCP 联调重试：
    - issue `#33`
    - PR `#35`
    - task `a987a809-a08e-409b-8162-0993f4a133fd`
    - 最终 `approved`
    - review_run：`9cff13b6-5ea6-46aa-b793-d6bd237be7a7`

- 通过：
  - `python -m unittest -v tests.test_llm_runtime tests.test_sleep_coding tests.test_automation tests.test_mvp_e2e tests.test_channel`
  - `python -m unittest -v tests.test_sleep_coding.GitWorkspaceServiceTests.test_dry_run_worktree_commit_push tests.test_mvp_e2e tests.test_runtime_components`
  - `python -m py_compile app/runtime/llm.py app/runtime/pricing.py app/services/main_agent.py app/services/sleep_coding.py app/services/sleep_coding_worker.py app/graph/workflow.py app/services/automation.py app/services/channel.py app/services/git_workspace.py`
  - 真实 `MiniMax + Feishu` 安全模拟脚本已执行，结果为 `approved`，ledger total tokens = `1424`
  - 真实 webhook 模拟脚本已执行：
    - `python - <<'PY' ... main_agent.intake(...) + automation.process_worker_poll_async(...) ... PY`
  - `python -m unittest -v tests.test_channel tests.test_feishu tests.test_mvp_e2e`
  - `python -m unittest -v tests.test_channel tests.test_feishu tests.test_automation tests.test_mvp_e2e`
  - `python -m unittest -v tests.test_main_agent tests.test_sleep_coding tests.test_review tests.test_mvp_e2e`
  - `python -m unittest -v tests.test_review tests.test_automation tests.test_mvp_e2e`
  - `python -m unittest -v tests.test_sleep_coding tests.test_mvp_e2e tests.test_feishu tests.test_automation.AutomationServiceTests.test_auto_review_approves_clean_pr_and_sends_final_delivery`
  - `python -m unittest -v tests.test_feishu tests.test_mvp_e2e tests.test_api.ApiTests.test_feishu_webhook_endpoint`
  - `python -m unittest -v tests.test_sleep_coding_worker`
  - `python -m unittest -v tests.test_sleep_coding.SleepCodingServiceTests.test_start_and_approve_plan_append_usage_to_kickoff_request tests.test_mvp_e2e tests.test_token_ledger`
  - `python -m unittest -v tests.test_mvp_e2e tests.test_token_ledger tests.test_review tests.test_api.ApiTests.test_gateway_message_endpoint tests.test_api.ApiTests.test_create_review_endpoint tests.test_api.ApiTests.test_trigger_sleep_coding_review_endpoint`
  - `python -m unittest -v tests.test_mvp_e2e tests.test_main_agent tests.test_automation.AutomationServiceTests.test_auto_review_approves_clean_pr_and_sends_final_delivery tests.test_api.ApiTests.test_gateway_message_endpoint tests.test_api.ApiTests.test_main_agent_intake_endpoint`
  - `python -m unittest -v tests.test_mvp_e2e tests.test_automation.AutomationServiceTests.test_auto_review_approves_clean_pr_and_sends_final_delivery tests.test_api.ApiTests.test_gateway_message_endpoint tests.test_api.ApiTests.test_main_agent_intake_endpoint tests.test_api.ApiTests.test_sleep_coding_worker_poll_endpoint tests.test_sleep_coding.SleepCodingServiceTests.test_start_and_approve_plan_append_usage_to_kickoff_request tests.test_review.ReviewServiceTests.test_trigger_for_sleep_coding_task_and_request_changes`
  - `python -m unittest -v tests.test_feishu`
  - `python -m unittest discover -s tests -v`
- 注意：
  - 全量 discover 已通过：`103` tests / `OK`
  - `tests.test_api` 仍会打印 `httpx` 请求日志，这是当前测试日志配置的正常输出，不再是外部 MCP / webhook 噪音

## 当前未完成

1. 继续收口 `feishu / gateway / task / review / final delivery` 五处 token 展示与聚合口径的 API/UI 外显细节；当前 MiniMax cached token 口径已修正，但还要继续看真实卡片是否足够易读
2. 继续补围绕 `feishu -> gateway -> issue -> claim -> coding -> review -> final delivery` 的主链路验收，并根据用户回传的真实飞书截图继续微调卡片文案、字段顺序与 token 展示
3. 继续追查 review `real_run` 失败原因；当前 GitHub MCP issue/PR 写入已再次真实验证通过，但 review 仍可能因 MiniMax TLS/网络问题回退到 `dry_run`
4. 继续减少剩余 service-style orchestration 逻辑

## 继续工作时优先看

1. `docs/status/current-status.md`
2. `docs/plans/mvp-execution-plan.md`
3. `docs/requirements/mvp-gap-analysis.md`
4. 本文档

## 当前风险与注意事项

- `platform.json` 仍应作为平台级配置事实来源，不要把联调 convenience 逻辑再做成环境变量覆盖平台默认
- `sleep_coding` 现在会在主事务提交后再写 ledger，避免 SQLite 锁等待；后续如果继续改 token 入账时序，不要回到“事务内跨连接写库”
- review usage 现在也会追加到账本；如果 task 没有 kickoff request，review 仍只会落在 review run 自身，不会强行创建伪 request
- gateway 包装 main-agent intake 的路径现在要求复用同一个 `request_id / run_id`；后续如果再改 `WorkflowRunner` 或 `MainAgentService`，不要把这条链重新拆成两份 request
- 后续如果再改 token 聚合接口，要继续保持“总量不冒充单 step”的语义；只有单步过滤结果才应该带 `step_name`
- 当前平台默认 `auto_approve_plan=true` 是为了保证 MVP 主闭环真实可跑；如果后续要恢复人工确认模式，应通过 `platform.json` 明确改回，而不是在代码里塞 source-specific override
- auto-approve 模式下已经不再发送 `ready for confirmation`；如果后续重新引入人工确认，必须显式区分“需要确认的 task”和“自动闭环 task”，避免通知语义再次混乱
- 当前 PR review 决策评论和 final delivery 工作总结已经更完整；后续如果继续改文案，要优先保持主链路信息闭环，不要把通知重新退化成纯状态播报
- 当前 issue prepared / PR ready / review decision / final delivery 四段都已带摘要信息；后续如果真实联调仍觉得“像半成品”，优先检查文案质量与真实仓库数据映射，而不是继续加新功能
- GitHub MCP 对新增未跟踪文件的 push 现在依赖 `--untracked-files=all`；后续如果再改 Git 变更采集逻辑，不能退回目录折叠模式，否则会再次出现“远端分支存在但没有 diff”的假成功
- 飞书目前已经是 card 模式；后续如果继续收口，只需要改 card 内容编排，不要把出站层重新做回纯文本
- 当前 card 已具备概览、分段、文件清单和 token 结构化展示；后续如果真实联调仍不够“成品”，优先继续改 card 文案和信息密度，而不是回到通知机制层
- 真实 webhook 模拟已经发出；下一步最有价值的输入不是更多猜测，而是用户返回的实际飞书截图
- 后台 follow-up 目前还是进程内线程池，不具备跨进程持久队列语义；服务重启后仍需靠 worker/claim 状态恢复
- 部分 API/测试路径如果没有先落 request ledger，再去追加 child-step usage，会出现“request not found”；当前实现仍是跳过而不是中断主流程
- 测试 helper 现在默认走 `app_env=test`；后续新增测试如果直接 `Settings()` 且不显式设 `app_env`，仍可能把真实 MCP / webhook 配置带回来

## 建议的下一步动作

1. 基于当前通过的主链路 smoke，继续补一组更贴近真实配置的 MVP smoke suite，重点覆盖 `feishu -> gateway -> issue -> claim -> coding -> review -> final delivery`
2. 继续核对 `feishu / gateway / task / review / final delivery` 的 token/cost 输出一致性，以及最终通知中的工作总结 / review 结果是否完整；特别是 issue `#33` / PR `#35` 这一轮的对外展示
3. 只修主链路阻塞问题，不在当前阶段继续扩 stuck-task / cancel / resume
4. 每轮结束继续更新本文件，保持“已完成 / 未完成 / 下一步”三段结构稳定
