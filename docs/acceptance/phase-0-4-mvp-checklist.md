# Phase 0-4 MVP Checklist

> 更新时间：2026-03-16
> 说明：本清单用于在 Phase 4 完成后执行第一阶段整体联调验证。

## 一、环境前置条件

- Python 3.11 / 3.12 环境可用
- `.env` 已配置数据库路径
- GitHub token 可选；未配置时允许 dry-run
- GitLab token 可选；未配置时允许 dry-run
- 飞书 webhook 可选；未配置时允许 dry-run
- review skill 命令可选；未配置时允许 dry-run

## 二、Gateway 基础验证

- [ ] `GET /health` 返回 `ok`
- [ ] `POST /gateway/message` 可处理 general intent
- [ ] `POST /gateway/message` 可处理 stats query intent
- [ ] Gateway 响应中带 `token_usage`

## 三、Sleep Coding 验证

- [ ] 可创建 sleep coding task
- [ ] task 可进入 `awaiting_confirmation`
- [ ] `approve_plan` 后可进入 coding / validating / pr_opened 路径
- [ ] PR 信息或 dry-run PR 信息可查询

## 四、Code Review 验证

- [ ] 可独立发起 review
- [ ] review 结果可写入本地 `docs/review-runs/` 运行目录
- [ ] GitHub / GitLab / local code 至少一类输入验证通过
- [ ] `request_changes` 可回流至 sleep coding

## 五、Token Ledger / Daily Report 验证

- [ ] 请求结束后 token usage 可写库
- [ ] `GET /reports/tokens?window=7d` 返回聚合结果
- [ ] `GET /reports/tokens?window=30d` 返回聚合结果
- [ ] `POST /reports/tokens/daily/generate` 可生成昨日日报
- [ ] `GET /reports/tokens/daily/{summary_date}` 可读取已生成日报
- [ ] 结构化结果与规则摘要一致

## 六、人工验证节点

- [ ] 飞书通知文案是否清晰
- [ ] review 结果是否符合预期格式
- [ ] token 成本口径是否符合当前 provider 计费约定
- [ ] dry-run 与 real-run 的状态提示是否足够明确

## 七、联调通过标准

- [ ] 四条主链路都可执行：Gateway / Sleep Coding / Code Review / Token Ledger
- [ ] 无阻塞性高危问题
- [ ] 文档、API、测试结果一致
