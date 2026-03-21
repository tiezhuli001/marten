# Docs

本目录只保留当前公开仓库需要的文档：

- `architecture/`: 长期有效的系统边界和状态模型
- `evolution/`: 当前仍有效的演进方向

公开树与内部工作内容请严格分离。`docs/internal/` 仅供在地 agent 交接、留痕或临时推演使用，原则上不应进入公开提交。新的临时文档默认不进入公开主文档树；若需要共享，先把核心结论搬到 `architecture/` 或 `evolution/`。

优先阅读顺序：

1. [evolution/mvp-evolution.md](evolution/mvp-evolution.md)
2. [architecture/mvp-agent-platform-core.md](architecture/mvp-agent-platform-core.md)
3. [architecture/github-issue-pr-state-model.md](architecture/github-issue-pr-state-model.md)

历史/过渡文档统一放在 `archive/`：

- [archive/architecture/mvp-agent-first-architecture.md](archive/architecture/mvp-agent-first-architecture.md)

清理原则：

- 不保留历史 phase 文档
- 不保留 requirements / plans 的阶段性副本
- 不保留 review 归档和运行产物
- 不保留一次性部署草稿和低信息密度说明文档

内部状态、hand-off 记录或临时探索性笔记请写在 `docs/internal/README.md`（仅面向在地 agent），并将公开引用指向这份本地索引。
