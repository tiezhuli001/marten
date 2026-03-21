# MVP Evolution

> 更新时间：2026-03-21
> 用途：只保留当前仍有效的演进方向，不重复描述当前架构现状或阶段性执行计划。

## 文档边界

这份文档不再负责解释：

- 当前架构长什么样
- 当前主链已经收口到什么程度
- 当前阶段验证通过了哪些实现事实
- 某一轮 cleanup 的分批执行计划

这些内容请分别看：

- [current-mvp-status-summary.md](../architecture/current-mvp-status-summary.md)
- [mvp-agent-platform-core.md](../architecture/mvp-agent-platform-core.md)
- `docs/archive/`

这份文档只回答一个问题：

在当前主链已经稳定之后，后续演进还应该继续把力气花在哪里？

## 演进方向没有变化

后续演进仍然应该围绕一个目标：

> 继续做减法，让 `Marten` 更像一个小而硬的 agent platform core，而不是重新长回大而散的自动化平台。

判断某项工作是否值得推进，优先看它是否强化下面这些方向：

- 是否继续减少 Python orchestration
- 是否继续减少并列真相源和历史兼容层
- 是否继续减少中间态文档和阶段性计划副本
- 是否继续让 agent 通过 prompt / workspace docs / MCP / skill 发挥能力
- 是否继续保护 `gateway -> main-agent -> ralph -> review -> delivery` 这条主链不被稀释

## 必须保留的复杂度

下面这些复杂度仍然是合理且必要的：

- `task / session / event` 控制面
- GitHub / GitLab / Feishu / MCP 集成边界
- worker 调度、幂等、重试、记账
- `review / delivery` 闭环的真实状态写回

## 应继续删除或压缩的复杂度

下面这些仍然应该被持续审查和压缩：

- agent 内部重复的 writeback / notification / formatting
- 只为兼容旧路径存在的 `services/*`
- 工程代码里对 agent 输出做过度兜底
- 历史阶段性需求分析、计划文档、部署草稿

## 近期演进顺序

1. 继续压 `Ralph` 的执行编排，减少它对细粒度 writeback 的直接感知
2. 继续压 `Code Review Agent` 的运行包装逻辑，坚持 skill-first
3. 持续审查 `app/services/*`，只保留稳定领域服务
4. 继续压缩配置和运行时兼容读取，坚持 canonical config
5. 让 docs 只保留架构、演进、状态三类公开文档；阶段性交接和执行计划只进本地目录或归档

## 文档策略

当前仓库文档只保留：

- 架构：长期有效的系统边界和状态模型
- 演进：当前仍有效的收敛方向
- 状态：当前真实实现、当前阶段结论和关键实现对照

以下内容不再保留在主分支：

- 阶段性 requirements 分析
- 临时 execution plan
- 中间产物 review 归档
- 一次性的部署草稿
- 仅面向在地 agent 的 handoff / 临时推演文档
- agent 目录说明这类低信息密度文档
