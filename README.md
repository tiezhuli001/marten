# youmeng-gateway

个人多 Agent 平台的网关与骨架仓库。

## Current Scope

当前仓库已经进入 `Phase 2` 睡后编程 MVP：

- FastAPI Gateway 最小入口
- LangGraph 主图骨架
- Sleep Coding 任务状态与事件落库
- GitHub Issue / PR dry-run 或真实回写
- Ralph 专属标签自动打到 Issue / PR
- 可选的 Channel 出站通知，默认兼容飞书 webhook
- Git worktree / commit / push 的 dry-run -> real-run 骨架
- worktree 内会生成 `.sleep_coding/issue-<number>.md` 作为最小可提交产物
- 计划生成、人工确认、本地验证、PR 打开流程
- token ledger 占位与任务级聚合

## Quick Start

```bash
conda create -n youmeng-gateway python=3.12
conda activate youmeng-gateway
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

推荐使用 `Python 3.11` 或 `3.12`。当前 LangGraph / LangChain 相关依赖在 `Python 3.14` 上仍有兼容性警告，不建议作为正式开发环境。

## Configuration

项目通过 `.env` 加载配置，模板见 `.env.example`。

关键配置项：

- `APP_ENV`: 运行环境标识
- `APP_PORT`: FastAPI 服务端口
- `APP_DATA_DIR`: 项目运行时数据目录，默认是项目根目录下的 `data/`
- `DATABASE_URL`: 当前默认使用 SQLite，例如 `sqlite:///data/youmeng_gateway.db`
- `LANGSMITH_TRACING`: 是否开启 LangSmith tracing
- `LANGSMITH_PROJECT`: LangSmith 项目名
- `LANGSMITH_API_KEY`: LangSmith API Key
- `GITHUB_TOKEN`: 后续 GitHub 自动化使用
- `CHANNEL_WEBHOOK_URL`: 可选的 Channel webhook，配置后会发送 sleep coding 状态通知
- `CHANNEL_PROVIDER`: Channel 提供方，默认 `feishu`
- `SLEEP_CODING_LABELS`: 逗号分隔的 GitHub 标签，默认 `agent:ralph,workflow:sleep-coding`
- `SLEEP_CODING_WORKTREE_ROOT`: sleep coding worktree 根目录，默认 `.worktrees/`
- `SLEEP_CODING_ENABLE_GIT_COMMIT`: 是否真实执行 `git worktree` / `git commit`
- `SLEEP_CODING_ENABLE_GIT_PUSH`: 是否真实执行 `git push`
- `GIT_REMOTE_NAME`: 推送远端名，默认 `origin`
- `REVIEW_RUNS_DIR`: code review agent 运行产物目录，默认 `docs/review-runs/`
- `REVIEW_SKILL_NAME`: 默认 `code-review`
- `REVIEW_SKILL_COMMAND`: 可选，自定义 review skill 执行命令
- `GITLAB_API_BASE`: GitLab API 地址，默认 `https://gitlab.com/api/v4`
- `GITLAB_TOKEN`: GitLab 评论回写使用

默认情况下，运行时文件会写入项目内的 `data/`。如果当前环境对项目目录没有写权限，代码会临时回退到系统临时目录，避免服务直接启动失败。

启动后可用接口：

- `GET /health`
- `POST /gateway/message`
- `GET /status/current`
- `POST /tasks/sleep-coding`
- `GET /tasks/sleep-coding/{task_id}`
- `POST /tasks/sleep-coding/{task_id}/actions`
