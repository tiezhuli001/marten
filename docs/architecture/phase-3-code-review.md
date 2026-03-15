# Phase 3 Design Prep: Code Review

> 更新时间：2026-03-15

## 目标

在 Sleep Coding MVP 能生成 PR 之后，本阶段补齐 review 回路。

## 设计重点

1. Review 不是简单总结 diff，而是给出可执行的审查结论
2. Review 输出要区分：
   - blocking issues
   - non-blocking suggestions
   - test gaps
3. `request_changes` 必须能够回流到 coding 节点

## 最小工作流

```text
PR created
-> collect diff
-> generate review summary
-> write PR comment
-> wait for user decision
-> approve / request_changes / cancel
```

## 推荐输出结构

- 变更摘要
- 风险点
- 潜在回归
- 测试缺口
- 建议结论

## 关键数据

- `review_status`
- `review_summary`
- `review_decision`
- `reviewed_at`
