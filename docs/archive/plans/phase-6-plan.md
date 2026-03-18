# Phase 6 Plan

> 阶段名称：中医养生 Agent
> 目标：验证“RAG + Skill 模板 + 结构化建议”型知识 Agent
> 对应设计：[phase-6-tcm-agent.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/architecture/phase-6-tcm-agent.md)

## 一、阶段目标

本阶段要构建的是一个知识型 agent，不是通用聊天助手。

完成后应具备：

1. 接收养生问题
2. 在内部 RAG 或外部检索中找到参考内容
3. 按固定结构输出建议
4. 保留风险提示和边界声明

## 二、范围

### 本阶段要做

- 养生问题识别
- RAG 检索
- skill 模板化输出
- 回答结构固定化

### 本阶段不做

- 医疗诊断替代
- 个性化治疗处方
- 长期病历记忆

## 三、核心任务

### Task 6.1 问题分类

- 识别养生问题
- 区分一般咨询和不应回答问题

### Task 6.2 RAG 检索

- 从中医知识库检索片段
- 对结果进行引用整合

### Task 6.3 Skill 输出模板

- 症状理解
- 养生建议
- 饮食建议
- 作息建议
- 风险提示

## 四、阶段产出

- TCM Agent workflow
- Skill 模板
- 引用式回答格式

## 五、阶段通过标准

- [ ] 可基于检索结果输出结构化回答
- [ ] 有固定风险提示
- [ ] 不越权给出医疗诊断
