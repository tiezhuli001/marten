# Current Status

> 更新时间：2026-03-16
> 当前阶段：Phase 4 已完成，进入 MVP 差距收口规划
> 当前目标：以 MVP 差距清单为基线，逐步补齐真实入口、真实模型执行与自动 agent loop

## 当前结论

- 主仓库已经确定：`youmeng-gateway`
- 开发主环境确定为：Linux 服务器
- 当前交互模式确定为：
  - `OpenClaw`: 沟通、进度反馈、飞书入口
  - `OpenCode`: 服务器上的交互式编码助手
  - `LangGraph + LangSmith`: 第一阶段编排与观测方案

## 已完成

- [x] 主仓库创建并拉取到本地
- [x] 正式迭代计划完成
- [x] `docs/` 目录骨架初始化
- [x] Phase 0 / Phase 1 执行 Plan 完成
- [x] Phase 1 平台骨架代码完成并阶段性提交
- [x] Phase 1 验收基线完成
- [x] Phase 2 第一版 Sleep Coding task/API/workflow 落地
- [x] Phase 2 Ralph 标签策略落地
- [x] Phase 2 Channel 出站通知骨架落地
- [x] Phase 2 git worktree / commit / push dry-run 骨架落地
- [x] Phase 2 worktree 任务产物生成骨架落地
- [x] Phase 2 PR #3 code review 归档并回写处置结果
- [x] Phase 3 文档校准为 skill 驱动 review 方案
- [x] Phase 4 文档补充整体 MVP 验证目标
- [x] Phase 3 独立 review 入口与运行产物目录设计落地
- [x] Phase 3 独立 code review agent 最小能力完成
- [x] Phase 4 implementation plan 归档
- [x] Phase 4 token ledger 扩展字段落地
- [x] Phase 4 7d / 30d token 查询接口落地
- [x] Phase 4 daily token summaries 聚合表落地
- [x] Phase 4 昨日日报生成入口落地
- [x] Phase 0-4 MVP 验证清单归档
- [x] MVP 差距清单归档
- [x] MVP 执行计划归档

## 正在进行

- [x] Phase 0-2 文档与实现对齐
- [x] Phase 3 需求校准：review 由 skill 执行，平台做回写与归档
- [x] Phase 4 需求校准：完成后先做 Phase 0-4 联调
- [x] Phase 3 编码计划归档
- [x] Phase 3 独立 review service / API 第一版落地
- [x] Phase 3 review-runs 运行产物目录落地
- [x] Phase 3 review skill 真正执行链路已接入
- [x] Phase 3 GitLab 评论回写接口已接入
- [x] Phase 4 token ledger 查询 / 报表 API 已完成
- [x] Phase 4 规则化 token 摘要已完成
- [x] 当前实现与目标 MVP 的能力差距已完成梳理
- [ ] GitLab 评论回写真实联调
- [ ] review skill 真实环境联调
- [ ] MVP-A 真实模型与 Feishu 入口实现

## 下一步

1. 实现统一模型执行层与真实 token/cost 记账
2. 实现 Feishu 真实对话入口
3. 实现 GitHub issue 创建链路
4. 再进入 Sleep Coding 自动 worker 与 auto review loop

## 当前阻塞

- 当前本机 `python3` 为 3.14，LangChain 生态有兼容性警告；正式环境应固定在 Python 3.11/3.12
- 飞书 Channel 还未配置真实 webhook，因此当前通知默认 dry-run
- 当前任务流还没有真实代码生成器，因此 commit 多数会以 skipped 结束
- Phase 3 已完成独立 review service 第一版，但真实 review skill 和 GitLab 回写仍未联通
- 未配置 provider / token / webhook 的环境下，GitHub、GitLab、review skill 仍会局部退回 dry-run
- daily token summary 已具备生成入口，但“每日 10 点”真实调度仍待联调环境验证
- 当前仍没有 OpenAI / Minimax 统一模型执行层，因此 token/cost 统计尚不具备真实精度
- 当前仍没有 Feishu 对话入口，因此用户还不能通过机器人直接驱动主 Agent
- 当前仍没有 GitHub issue 创建链路，因此“需求 -> issue -> coding”主路径还未打通

## 当前技术决定

- 第一阶段不直接做 `Feishu -> OpenClaw -> OpenCode 自动编码`
- 第一阶段先做：
  - 文档体系
  - 环境体系
  - 平台骨架
  - 最小意图路由与状态读取
- Phase 2 先做单任务、单仓库、人工确认的睡后编程 MVP
- Phase 2 允许向 Channel 发送出站通知，但不在飞书内做审批闭环
- Ralph 识别策略优先落在 GitHub Issue / PR 标签，而不是给 git 分支本身增加额外“标签”概念
- Phase 3 采用 skill 驱动 review，平台只做最小状态、归档、回写和流转
- `code review agent` 是独立能力，sleep coding 只是其触发来源之一
- `docs/code-review/` 与 `docs/review-runs/` 目录职责分离
- 第一阶段真正的需求验证节点放在 Phase 4 结束后统一执行
- 后续编码以 Phase 文档为唯一阶段基线，先补文档再补实现
- 数据层策略为：`Phase 1 / Phase 2` 先 SQLite，后续再迁移 PostgreSQL
- Phase 4 的 token ledger 采用确定性工程实现，规则摘要不依赖 skill 或 LLM
- 进入 MVP 收口阶段后，issue 理解、计划、编码、review、repair 等认知工作优先交给 LLM + skill + MCP
- Feishu 鉴权、token 账本、调度、幂等、状态机等基础设施继续保持工程化实现

## 当前事实来源

本文件是当前阶段状态的主事实来源。OpenClaw 后续应优先读取本文件回答：

- 当前做到哪了？
- 现在在做什么？
- 下一步做什么？
