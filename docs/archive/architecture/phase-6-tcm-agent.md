# Phase 6 Design Prep: TCM Agent

> 更新时间：2026-03-15

## 目标

构建基于中医养生知识库的结构化回答 agent。

## 最小工作流

```text
detect wellness question
-> retrieve relevant knowledge
-> apply skill template
-> produce structured answer
```

## 设计重点

1. 输出结构固定，避免泛泛而谈
2. 必须带风险提示
3. 不越界提供医疗诊断

## 推荐回答结构

- 问题理解
- 参考依据
- 养生建议
- 饮食建议
- 作息建议
- 风险提示
