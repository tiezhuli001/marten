# MVP Evolution

> 更新时间：2026-03-19
> 用途：保留当前仍有价值的演进结论，替代旧的 `plans/` 和 `requirements/` 分散文档。

## 目标没有变化

当前项目目标仍然是把 `Marten` 收口成一个极简的 agent-first 仓库：

- `channel -> control plane -> runtime -> agent`
- `LLM + MCP + skill` 优先
- Python 只保留状态机、集成边界、记账和调度这类必要复杂度

真实主链路保持不变：

`Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`

## 已经完成的演进

- 主链路已经打通，并有测试覆盖到 `review -> final delivery`
- 目录边界已经收口为 `app/channel`、`app/control`、`app/runtime`、`app/agents`、`app/infra`
- `main-agent`、`ralph`、`code-review-agent` 已成为明确的 agent 边界
- GitHub 主写路径已经收口为 `MCP + bridge`，不再保留历史 direct API service
- review skill 已改成 strict JSON-first，工程代码不再负责把半结构化文本“猜成结构化结果”
- 一批历史兼容 facade 和历史文档已经从当前分支移除

## 当前阶段

当前不是“继续补功能”的阶段，而是“继续做减法”的阶段。

下一阶段的判断标准不是：

- 又拆了几个 helper
- 又引入了几个 service

而是：

- 是否继续减少 Python orchestration
- 是否继续减少 `app/services/*`
- 是否继续减少中间态文档
- 是否让 agent 更多通过 prompt / workspace docs / MCP / skill 发挥能力

## 继续瘦身的原则

必须保留的复杂度：

- `task / session / event` 控制面
- GitHub / GitLab / Feishu / MCP 集成边界
- worker 调度、幂等、重试、记账
- `review / delivery` 闭环的真实状态写回

应该继续删除或压缩的复杂度：

- agent 内部重复的 writeback / notification / formatting
- 只为兼容旧路径存在的 `services/*`
- 工程代码里对 agent 输出做过度兜底
- 历史阶段性需求分析、计划文档、部署草稿

## 当前收敛顺序

1. 继续压 `Ralph` 的执行编排，减少它对细粒度 writeback 的直接感知
2. 继续压 `Code Review Agent` 的运行包装逻辑，坚持 skill-first
3. 持续审查 `app/services/*`，只保留稳定领域服务
4. 让 docs 只保留架构、演进、状态、交接四类文档

## 文档策略

当前仓库文档只保留：

- 架构：长期有效的系统边界和状态模型
- 演进：当前仍有效的收敛方向
- 状态：当前真实进度、验证结论和风险
- 交接：下一位 agent 接手需要的最小事实集

以下内容不再保留在主分支：

- 阶段性 requirements 分析
- 临时 execution plan
- 中间产物 review 归档
- 一次性的部署草稿
- agent 目录说明这类低信息密度文档
