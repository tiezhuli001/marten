# Docs

本目录只保留当前 MVP 收口所需的高信号文档。历史 phase 文档和中间迁移方案已经从当前分支移除，避免继续放大主 PR。

## 当前入口

优先阅读顺序：

1. `status/current-status.md`
2. `status/session-handoff.md`
3. `plans/capability-gap-and-optimization-plan.md`
4. `plans/mvp-execution-plan.md`
5. `requirements/mvp-gap-analysis.md`
6. `architecture/mvp-agent-first-architecture.md`
7. `architecture/github-issue-pr-state-model.md`
8. `runbooks/server-setup.md`

## 目录说明

- `status/`: 当前阶段事实来源与会话交接
- `plans/`: 当前仍有效的执行计划
- `requirements/`: 当前 MVP 需求边界与差距分析
- `architecture/`: 当前仍生效的架构与状态模型
- `runbooks/`: 部署与环境说明
- `agents/`: Agent 职责边界与工作区说明
- `acceptance/`: 当前保留的验收清单
- `code-review/`: 历史外部 review 归档

## 关于 Review 产物

`docs/review-runs/` 仍然是 code review agent 的默认运行产物目录，但它属于运行时文件，不再纳入版本控制。

如果需要检查本机运行产物：

1. 直接查看本地 `docs/review-runs/`
2. 以代码、测试结果和 `status/current-status.md` 为最终事实来源
