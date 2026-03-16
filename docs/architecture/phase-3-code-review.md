# Phase 3 Design Prep: Code Review

> 更新时间：2026-03-16

## 目标

在 Sleep Coding MVP 能生成 PR 之后，本阶段补齐 review 回路。

但 `code review agent` 本身是独立能力，不依附于 sleep coding。

本阶段的设计前提是：

> review 内容由既有 `code-review` skill 产生，平台负责组织输入、接收输出、归档和驱动后续流转。

## 设计重点

1. Code review agent 是独立入口，sleep coding 只是它的一个触发来源
2. Review skill 是执行器，不是平台数据库的一部分
3. 平台只保存最小必要状态，不做重型 findings 存储
4. agent 运行产物应落到：
   - GitHub / GitLab comment
   - `docs/review-runs/*.md`
5. `docs/code-review/` 保留给外部模型 / 人工 review 归档，不与 agent 运行产物混用
6. `request_changes` 必须能够回流到 coding 节点

## 最小工作流

```text
review request received
-> collect source link / local diff context
-> invoke code-review skill
-> receive markdown review
-> archive to docs/review-runs
-> write GitHub / GitLab comment if applicable
-> wait for user decision
-> approve / request_changes / cancel
```

## 推荐输出结构

skill 输出建议统一为 markdown，至少包含：

- 基本信息
- 变更摘要
- findings（P0-P3）
- summary
- 建议结论

## 平台最小状态

平台需要跟踪的只保留：

- `review_status`
- `review_decision`
- `reviewed_at`
- `review_artifact_path`
- `review_comment_url`
- `review_source_type`

## 为什么不做重型 review 建模

当前阶段的主要需求是：

1. 可执行一次 review
2. 可归档
3. 可回写 GitHub / GitLab 评论
4. 可回流修复

因此更合适的方式是：

- 把 review 原文保存为 markdown 文档
- 用最小状态字段驱动工作流
- 避免过早引入 `review_findings` 等复杂表结构

## 目录边界

- `docs/code-review/`: 外部模型 / 人工 review 归档
- `docs/review-runs/`: 平台内 code review agent 的运行产物

## 多 Agent 协作约定

`docs/review-runs/` 目录作为 agent review 事实源时，应满足：

- 每份 review 文档都能映射到 task / PR / 分支
- 文档中要区分 `已修复 / 暂不修复 / 无需修复`
- 最终事实仍以代码、测试结果和 `docs/status/current-status.md` 为准
