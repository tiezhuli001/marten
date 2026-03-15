# Phase 2 Plan

> 阶段名称：睡后编程 MVP
> 目标：跑通 GitHub Issue -> 计划 -> 编码 -> PR -> 人工确认 的最小闭环
> 对应设计：[phase-2-sleep-coding-mvp.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/architecture/phase-2-sleep-coding-mvp.md)

## 一、阶段目标

本阶段要证明平台已经不只是“能接请求”，而是能完成一个受控的软件工程任务闭环。

完成后应具备：

1. 从 GitHub Issue 启动 sleep_coding 任务
2. 生成可审阅的实施计划
3. 在独立分支上完成代码修改
4. 执行最小本地验证
5. 自动创建 PR
6. 把状态和 token 消耗沉淀下来

## 二、范围

### 本阶段要做

- GitHub Issue 读取与创建
- Sleep Coding task 状态表
- 计划生成与回写
- 独立工作分支策略
- 本地验证执行
- PR 创建
- 人工确认节点

### 本阶段前置假设

- 仍允许先使用 SQLite 持久化任务状态
- 正式 worker / queue 可以先不拆独立服务
- review 只要求最小回路，不要求完整 Code Review Agent

### 本阶段不做

- 自动 merge 到 `main`
- 多任务并发编排
- 飞书内审批闭环
- 自动回滚和复杂自修复

## 三、核心任务

### Task 2.1 Sleep Coding Task 数据模型

目标：

- 建立 `sleep_coding_tasks` 和 `task_events` 最小表

验收：

- [ ] 任务可生成 `task_id`
- [ ] 任务状态可持久化

### Task 2.2 GitHub Issue 集成

目标：

- 能读取指定 Issue 并建立本地任务

验收：

- [ ] 能用 `issue_number` 启动任务
- [ ] 能把计划摘要回写 Issue 评论

### Task 2.3 计划生成节点

目标：

- 在编码前输出可审阅计划

验收：

- [ ] 计划结构包含范围、验证方式、风险
- [ ] 用户可明确 approve / reject

### Task 2.4 编码工作目录与分支策略

目标：

- 固定工作分支和工作目录策略

建议：

- 分支格式：`codex/issue-<number>-sleep-coding`
- 工作目录与主仓库分离，避免污染当前分支

验收：

- [ ] 任务在独立分支运行
- [ ] 不污染 `main`

### Task 2.5 本地验证与 PR 创建

目标：

- 编码完成后执行最小验证，并自动创建 PR

验收：

- [ ] 能记录本地测试结果
- [ ] 能创建真实 PR
- [ ] PR 描述包含计划摘要、验证结果和关联 Issue

### Task 2.6 人工确认与结束记账

目标：

- 保留人为最终控制权

验收：

- [ ] 支持 approve / request_changes / cancel
- [ ] 任务结束时能写回 token 聚合

## 四、推荐执行顺序

1. 任务状态表
2. GitHub Issue 集成
3. 计划生成与回写
4. 工作目录与分支策略
5. 本地验证与 PR 创建
6. 人工确认与记账

## 五、阶段产出

- `sleep_coding_tasks` 最小表
- `task_events` 最小表
- Sleep Coding workflow 第一版
- GitHub Issue / PR 回写能力
- Phase 2 验收文档草案

## 六、阶段通过标准

- [ ] 可从一个真实 Issue 发起任务
- [ ] 可生成计划并回写 GitHub
- [ ] 可在独立分支完成代码变更
- [ ] 可自动创建 PR
- [ ] 可写回任务状态和 token 汇总
