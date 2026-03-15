# Phase 7 Design Prep: Metaphysics Agent

> 更新时间：2026-03-15

## 目标

基于可配置分析维度和文档依据，生成步骤化八字分析结果。

## 最小工作流

```text
detect metaphysics question
-> load configured dimensions
-> run ordered analysis steps
-> retrieve supporting references
-> generate step-by-step answer
```

## 设计重点

1. 维度配置要外部化
2. 每一步需要可解释输出
3. 文档引用和规则步骤同时保留

## 关键对象

- `metaphysics_profiles`
- `analysis_dimensions`
- `analysis_runs`
