# Docs

本目录只保留当前公开仓库需要的文档：

- `architecture/`: 长期有效的系统边界和状态模型
- `evolution/`: 当前仍有效的演进方向
- `archive/`: 历史方案和阶段性计划归档

公开树与内部工作内容请严格分离。`docs/internal/` 只应作为本地开发目录存在，不是公开文档树的一部分；需要共享的内容，应先提炼后写入 `architecture/` 或 `evolution/`。

优先阅读顺序：

1. [architecture/current-mvp-status-summary.md](architecture/current-mvp-status-summary.md)
2. [architecture/mvp-agent-platform-core.md](architecture/mvp-agent-platform-core.md)
3. [architecture/github-issue-pr-state-model.md](architecture/github-issue-pr-state-model.md)
4. [architecture/framework-positioning-and-private-agent-layering.md](architecture/framework-positioning-and-private-agent-layering.md)
5. [evolution/mvp-evolution.md](evolution/mvp-evolution.md)
6. [evolution/framework-package-and-private-agent-rollout-plan.md](evolution/framework-package-and-private-agent-rollout-plan.md)

历史/过渡文档统一放在 `archive/`：

- [archive/README.md](archive/README.md)
- [archive/architecture/mvp-agent-first-architecture.md](archive/architecture/mvp-agent-first-architecture.md)

清理原则：

- 不保留历史 phase 文档
- 不保留 requirements / plans 的阶段性副本
- 不保留 review 归档和运行产物
- 不保留一次性部署草稿和低信息密度说明文档
- 不把内部 handoff、执行计划、临时推演直接放进公开文档树
