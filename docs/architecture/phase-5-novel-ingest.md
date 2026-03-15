# Phase 5 Design Prep: Novel Ingest Agent

> 更新时间：2026-03-15

## 目标

把外部小说内容以“检索 -> 确认 -> 抽取 -> 入库”的方式纳入 RAG。

## 最小工作流

```text
search novel by name
-> return candidate list
-> user confirms target
-> extract content
-> chunk text
-> write vector store
```

## 设计重点

1. 用户确认必须保留
2. 元数据要保留小说名、章节、来源
3. 入库前要做文本切分和去重

## 核心实体

- `novel_search_jobs`
- `novel_extract_jobs`
- `rag_documents`
