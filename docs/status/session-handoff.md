# Session Handoff

> 更新时间：2026-03-18
> 用途：为下一位继续此任务的 LLM 提供压缩后的接手摘要。

## 1. 当前进展

- 当前主目标仍是收口并稳定 MVP 主链路：
  `feishu/gateway -> issue -> claim -> coding -> review -> final delivery`
- 代码侧主链路已经存在，且真实链路已验证过：
  - GitHub MCP issue/PR 真联调通过过
  - Sleep Coding worker claim / coding / PR / review / final delivery 主流程已跑通
  - LLM 失败语义已收口为：正式环境显式失败，`app_env=test` 可控回退
- 本轮新完成：
  - 提交 `48ab6ae`：`Trim non-essential MVP docs from branch`
  - 删除了不应继续压在当前 PR 上的文档噪音：
    - `docs/archive/**`
    - `docs/architecture/config-layer-refactor-and-migration.md`
    - `docs/architecture/multi-agent-platform-roadmap.md`
    - `docs/architecture/multi-agent-refactor-plan.md`
    - `docs/plans/mcp-config-and-workspace-hardening-plan.md`
  - 同步收口了：
    - `README.md`
    - `docs/README.md`
    - `docs/agents/README.md`
    - `docs/status/current-status.md`
    - `docs/status/session-handoff.md`

## 2. 已做出的关键决策

- 文档层只保留当前 MVP 有效事实来源，不再在当前分支保留历史 phase 文档或中间迁移方案。
- `docs/review-runs/` 是运行时产物目录，不再纳入版本控制。
- GitHub/GitLab 外部写操作坚持 MCP-only，配置入口坚持 `mcp.json`，不回退 REST / `GITHUB_TOKEN`。
- 配置继续保持 JSON-first：
  `agents.json / models.json / platform.json / mcp.json`
- LLM 请求层统一 timeout/retry 已在 shared runtime 中实现：
  默认 3 次尝试 + 指数退避，配置来源是 `platform.json`。

## 3. 用户偏好与约束

- 用户偏好：
  - 多 agent 架构
  - `LLM + MCP + skill` 优先
  - JSON-first
  - 不要把实际配置文件提交进仓库
  - 当前 PR 要尽量减压、避免“大平台全集”式膨胀
- 用户明确接受的处理顺序：
  1. 先清理文档噪音
  2. 再评估代码侧哪些非主链路能力能安全剥离
- 当前不要做的事：
  - 不要重新引入 REST fallback
  - 不要把未来 domain agent（Novel/TCM/Metaphysics）相关规划重新带回当前 PR
  - 不要为了缩 PR 乱删主链路核心代码

## 4. 剩余工作

明确下一步：

1. 评估并决定是否从当前 PR 剥离 `diagnostics`
   - 目前判断：可以安全剥离
   - 涉及：
     - `app/services/diagnostics.py`
     - `/diagnostics/integrations`
     - `tests/test_api.py` 中对应 endpoint 测试
     - README / runbook / requirements / status 中对应引用

2. 评估 `scheduler` 是否应从当前 PR 剥离
   - 目前判断：不建议直接剥离
   - 原因：
     - `app/main.py` 生命周期已引用 `WorkerSchedulerService`
     - `app/api/routes.py` 暴露了 `/workers/sleep-coding/run-once`
     - config/test/docs 已有配套引用
     - 它虽非认知主链路，但已成为 worker 自动推进的运行支撑

3. 如用户确认，下一轮执行顺序建议：
   - 先移除 `diagnostics`
   - 保留 `scheduler`
   - 再看 PR 体量是否已足够下降

## 5. 关键参考信息

- 当前主事实来源：
  - `docs/status/current-status.md`
  - `docs/status/session-handoff.md`
  - `docs/plans/mvp-execution-plan.md`
  - `docs/requirements/mvp-gap-analysis.md`
  - `docs/architecture/mvp-agent-first-architecture.md`
  - `docs/architecture/github-issue-pr-state-model.md`
- 与当前判断直接相关的代码：
  - `app/main.py`
  - `app/api/routes.py`
  - `app/services/diagnostics.py`
  - `app/services/scheduler.py`
  - `tests/test_api.py`
  - `tests/test_scheduler.py`
- 当前分支：`codex/mvp-gap-plan`
- 最近相关提交：
  - `48ab6ae` `Trim non-essential MVP docs from branch`
  - `32a4993` `Prune historical docs and review artifacts`
  - `b3b957d` `Finalize agent-first MVP runtime and workflow`
  - `580c9e9` `Tighten LLM failure handling for agent workflow`

## 6. 当前状态检查

- 这份交接文档是在提交 `48ab6ae` 之后重写的。
- 若下一位 LLM 接手，优先先看 `git status`，因为本文件当前是本轮新改动，尚未再次提交。
