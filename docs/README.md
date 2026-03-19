# Docs

本目录只保留当前公开仓库需要的文档：

- `architecture/`: 长期有效的系统边界和状态模型
- `evolution/`: 当前仍有效的演进方向

对内 handoff、临时状态、工作草稿统一放到 `docs/internal/`，并在 `.gitignore` 中忽略。

优先阅读顺序：

1. [evolution/mvp-evolution.md](evolution/mvp-evolution.md)
2. [architecture/mvp-agent-first-architecture.md](architecture/mvp-agent-first-architecture.md)
3. [architecture/github-issue-pr-state-model.md](architecture/github-issue-pr-state-model.md)

清理原则：

- 不保留历史 phase 文档
- 不保留 requirements / plans 的阶段性副本
- 不保留 review 归档和运行产物
- 不保留一次性部署草稿和低信息密度说明文档
