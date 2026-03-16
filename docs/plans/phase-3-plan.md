# Phase 3 Plan

> 阶段名称：Code Review 能力
> 目标：补齐睡后编程后的 review 回路，形成受控的软件工程交付链
> 对应设计：[phase-3-code-review.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/architecture/phase-3-code-review.md)

## 一、阶段目标

本阶段要实现的是一个独立的 `code review agent`，而不是 sleep coding 的附属子模块。

它应支持三类输入：

1. 外部 GitHub PR 链接
2. 外部 GitLab MR/PR 链接
3. 本地代码目录 / 本地分支 diff

同时，sleep coding 产出的 PR 也应能够触发这个 agent，但这只是触发来源之一。

本阶段的核心不是“自研一个复杂 reviewer 引擎”，而是：

> 以现有 `code-review skill` 作为 review 执行器，由平台负责触发、输入组织、结果归档、评论回写和决策流转。

完成后应具备：

1. 能独立对 GitHub / GitLab / 本地代码发起一次 code review
2. 能对 sleep coding 产出的 PR 触发同一套 review agent
3. 能把 review 结果回写到 PR / MR
4. 能把 review 结果归档为 agent 运行产物
5. 能跟踪最终 review 决策
6. 能把 `request_changes` 接回 sleep_coding

## 二、范围

### 本阶段要做

- 独立 Code Review Agent 入口
- Review skill 调用封装
- Review 最小状态模型
- Review 结果运行产物归档
- GitHub / GitLab 评论回写
- `request_changes` -> 重新编码 流转
- Review 决策持久化

### 本阶段前置依赖

- `Phase 2` 已能稳定创建 PR
- PR 与 task 已建立一一关联
- 本地验证结果可回写到 PR 或数据库
- 可从运行环境调用现有 `code-review` skill

### 本阶段不做

- 自研完整 review engine
- 完整静态分析平台
- 安全审计深度能力
- 多 reviewer 协作策略
- findings 明细级数据库建模
- 将 `docs/code-review/` 与 agent 运行产物混用

## 三、核心任务

### Task 3.1 Code Review Agent 入口

目标：

- 提供独立的 code review 入口，不绑定 sleep coding

支持输入：

- GitHub PR 链接
- GitLab MR/PR 链接
- 本地仓库路径 / 分支信息

验收：

- [ ] review agent 可被独立触发
- [ ] sleep coding PR 可复用同一入口

### Task 3.2 Review 最小状态建模

目标：

- 仅保留平台编排必须的 review 状态，不做重型数据建模

建议字段：

- `review_status`
- `review_decision`
- `reviewed_at`
- `review_artifact_path`
- `review_comment_url`
- `review_source_type`

验收：

- [ ] review 生命周期状态可查询
- [ ] review 结果文档位置可追踪

### Task 3.3 Review Skill 调用与结果标准化

目标：

- 调用既有 `code-review` skill，对 GitHub / GitLab / 本地 diff 执行一次只读审查

要求：

- skill 输出统一为 markdown
- 统一包含 findings、summary、建议结论
- 不在平台内重复实现一套 review 引擎

验收：

- [ ] GitHub / GitLab / 本地代码均可触发 skill review
- [ ] skill 输出可被平台接收并标准化

### Task 3.4 Review 结果归档与评论回写

目标：

- 将 review 结果同时沉淀到平台运行产物和代码托管平台评论

要求：

- GitHub / GitLab comment 可读
- `docs/review-runs/` 中有归档文件
- 文档中要标明来源类型、task / PR / MR / 分支

验收：

- [ ] review 结果可写回 GitHub / GitLab 评论
- [ ] review 结果可归档到 `docs/review-runs/`

### Task 3.5 Review 决策流转

目标：

- 支持 `approve`
- 支持 `request_changes`
- 支持 `cancel`

要求：

- `request_changes` 回流到 coding
- 不丢失上一轮 review 文档
- review 决策可持久化

验收：

- [ ] `request_changes` 可回流至 coding
- [ ] review 决策可持久化

## 四、阶段产出

- 独立 Code Review Agent 入口
- Review skill 调用封装
- Review 最小状态模型
- GitHub / GitLab 评论回写能力
- `docs/review-runs/` 归档规范
- changes requested 回流机制

## 五、阶段通过标准

- [ ] GitHub / GitLab / 本地代码至少两类输入可跑通 review
- [ ] sleep coding PR 可触发同一套 review agent
- [ ] review 结果可同时写回评论与 `docs/review-runs/`
- [ ] `request_changes` 可回流至 coding
- [ ] 最终 review 决策可持久化
