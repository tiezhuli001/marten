# RAG Provider Surface Rollout Plan

> **For agentic workers:** REQUIRED: Use handoff docs plus current architecture docs while executing. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `Marten` 的 RAG capability 收口成统一 provider surface，并为 `Qdrant` first / `Milvus` ready 的实现路线提供可执行计划。

**Architecture:** 调用面统一进入 `RAGFacade`，provider 只做 adapter，后处理统一处理，embedding 与向量库解耦。

**Tech Stack:** Python runtime, `app/rag/retrieval.py`, provider adapters, vector backends such as Qdrant and Milvus.

---

## Chunk 1: Contract 收口

### Task 1: 定义统一 request / response shape

**Files:**
- Create or modify later: `app/rag/retrieval.py`
- Reference: `docs/architecture/rag-provider-surface.md`

- [x] Step 1: 定义 `RetrievalRequest`
- [x] Step 2: 定义 `RetrievedDocument`
- [x] Step 3: 定义 `RetrievalResponse`
- [x] Step 4: 检查调用方不再依赖具体向量库参数

### Task 2: 收口 provider interface

**Files:**
- Modify later: `app/rag/retrieval.py`

- [x] Step 1: 定义统一 `search` / `fetch` adapter contract
- [x] Step 2: 区分必选能力与可选 capability
- [x] Step 3: 保持 `InMemoryRetrievalProvider` 继续作为测试基线

## Chunk 2: 后处理统一

### Task 3: 从 provider 中抽离统一后处理

**Files:**
- Modify later: `app/rag/retrieval.py`
- Add later as needed: `app/rag/postprocess.py`

- [x] Step 1: 统一 dedupe
- [x] Step 2: 统一 cross-domain merge
- [x] Step 3: 统一 citation shaping
- [x] Step 4: 统一 token budgeting / merge policy

## Chunk 3: Provider Rollout

### Task 4: Qdrant First

**Files:**
- Add later: `app/rag/providers/qdrant.py`
- Add later: config docs/tests

- [x] Step 1: 先做最小 `Qdrant` adapter
- [x] Step 2: 跑通 `Operational RAG`
- [x] Step 3: 增加最小回归测试

### Task 5: Milvus Runtime

**Files:**
- Add later: `app/rag/providers/milvus.py`

- [x] Step 1: 固化 `Milvus` adapter 所需输入输出
- [x] Step 2: 确保 facade contract 无需修改
- [x] Step 3: 接通本地 `Milvus Lite`，补 `search / fetch` 映射、配置装配与真实 smoke test

## Verification

- [x] `sed -n '1,280p' docs/architecture/rag-provider-surface.md`
- [x] `sed -n '1,260p' docs/evolution/rag-provider-rollout-plan.md`
- [x] `sed -n '1,320p' docs/plans/2026-03-22-rag-provider-surface-rollout.md`
- [x] `sed -n '1,260p' app/rag/retrieval.py`

## Done Criteria

- 当前文档已经明确 facade / provider / post-process 的边界
- `Qdrant` adapter 已真实落地并完成回归验证
- `Milvus Lite` 已真实落地并保持 facade contract 不变
- 后续接远端 `Milvus` 时不需要重新设计调用 contract
