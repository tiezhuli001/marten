# Post MVP Slimming Cleanup Plan

> 更新时间：2026-03-20
> 目标：在当前 MVP 主链稳定后，继续删除历史代码、历史文档和冗余抽象。

## Batch 1: 收缩 review contract

- review 对外输入只保留 `task_id`。
- `repo/pr_number/url/local_path/base_branch/head_branch` 全部改为内部派生。
- 继续删除 review 说明文字和 artifact 中残留的非 GitHub 语义。

## Batch 2: 下线主链旁路写入口

- 评估并逐步下线绕开 `gateway -> main-agent -> ralph -> review` 的直接写接口。
- 优先保留读接口，减少外部直接推进内部阶段的 API。
- 保持主链 handoff 为唯一推荐入口。

## Batch 3: 收敛状态真相源

- 评估 `control_tasks + control_task_events` 是否升级为唯一控制真相。
- 逐步降低 `sleep_coding_tasks` 和 `review_runs` 对主编排的驱动作用。
- 删除只为历史观察链路保留、但不再被消费的事件。

## Batch 4: 收紧运行时兼容层

- 收紧 `models.json` provider / model 配置，只保留 canonical key。
- 删除历史 provider alias 和过宽兼容读取。
- 审计 Ralph / Review 的多执行路径，逐步统一成单一路径。

## Batch 5: 文档归档

- 以 `mvp-agent-platform-core` 为主文档。
- 将 `mvp-agent-first-architecture` 迁到归档位或明确标注为历史方案稿。
- 保证公开文档只描述当前真实实现，不再把未来设计写成现状。
