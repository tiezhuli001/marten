# RAG Provider Runtime Handoff

## Goal

- 保持 `RAGFacade` 调用面不变，继续在统一 provider surface 下推进多向量库能力
- 当前已经完成 `Qdrant` 与本地 `Milvus Lite` 的真实接入，下一轮应在此基础上规划远端 `Milvus` 部署切换、provider 观测性或更强检索能力

## Current State

- 当前阶段：`Qdrant first + Milvus Lite runtime landed`
- 当前 owner：下一位继续执行 RAG / runtime / infra 的 agent
- 当前 task / issue / PR / review id：无单独 issue / PR；以当前工作区未提交变更和 `STATUS.md` 为准

## Source Of Truth

- Architecture:
  - `docs/architecture/rag-provider-surface.md`
  - `docs/architecture/agent-system-overview.md`
  - `docs/architecture/agent-runtime-contracts.md`
- Plan:
  - `docs/evolution/rag-provider-rollout-plan.md`
  - `docs/plans/2026-03-22-rag-provider-surface-rollout.md`
- Repo / Workspace:
  - `/Users/litiezhu/workspace/github/marten`
- Runtime / Config:
  - `platform.json`
  - `app/rag/retrieval.py`
  - `app/rag/providers/qdrant.py`
  - `app/rag/providers/milvus.py`
  - `app/rag/indexing.py`
  - `scripts/index_docs_to_qdrant.py`
  - `scripts/index_docs_to_milvus.py`
  - `STATUS.md`

## Completed

- `Qdrant` provider 已真实接入，`RAGFacade -> Qdrant` 检索正常
- `MilvusRetrievalProvider` 已真实接入本地 `Milvus Lite`
- `Milvus` provider 已支持：
  - `uri`
  - `token`
  - `db_name`
  - `vector_field`
  - `primary_field`
  - `search_params`
  - 本地 embedding 模型配置
- `search/fetch` 映射已通过单测和真实 smoke test
- `platform.json` 已可装配：
  - `local-qdrant`
  - `local-milvus`
  - `repo-docs`
  - `repo-docs-milvus`
- 文档索引已抽出共享模块 `app/rag/indexing.py`
- `Qdrant` / `Milvus` 索引脚本都具备：
  - markdown chunk 收集
  - stable item id
  - manifest 驱动的增量同步
  - 最小 schema / vector dim 守卫
- 已修复重复标题 chunk 的 stable id 冲突问题
- 当前索引状态：
  - `Qdrant`: `chunks_upserted=0`, `chunks_deleted=0`, `chunks_unchanged=413`
  - `Milvus`: `chunks_upserted=0`, `chunks_deleted=0`, `chunks_unchanged=413`

## In Progress

- 无

## Next Step

- 如果下一轮要推进 `Milvus` 生产化，优先补“Milvus Lite 本地模式”和“远端 Milvus Standalone/Distributed”之间的配置切换与运行手册
- 如果下一轮要推进检索效果，优先补 provider 级 filter compatibility、rerank 和 retrieval observability

## Acceptance / Validation

- 当前完成标准：
  - `RAGFacade` 调用面不变
  - `Milvus` contract 接入完成
  - 本地索引具备增量同步与 schema 守卫
  - 相关测试全部通过
- 已执行验证：
  - `python scripts/index_docs_to_qdrant.py`
  - `python scripts/index_docs_to_milvus.py`
  - `python - <<'PY' ... repo-docs-milvus policy ... RAGFacade(...).retrieve_response(...) ... fetched=... PY`
  - `python -m unittest tests.test_rag_indexing tests.test_rag_capability tests.test_runtime_components tests.test_framework_public_surface tests.test_automation -v`
- 尚未执行但下一轮可能需要的验证：
  - 远端 `Milvus`（非 Lite）连接与索引 smoke test
  - 多 provider 切换下的 filter / latency / hit-rate 回归

## Risks / Blockers

- 当前 blocker：None
- 当前风险：
  - `Milvus Lite` 是本地文件库，不适合被多个独立进程长期并发打开同一 `.db`
  - 如果切远端 `Milvus`，需要额外明确 host/port/token/db_name 的部署约束

## Immediate First Action

- 下一位 agent 接手后先读 `STATUS.md`、本 handoff 和 `docs/architecture/rag-provider-surface.md`，再决定是继续补远端 `Milvus` 手册，还是推进 retrieval 效果与观测性

## Notes

- 当前本地 `Milvus` 数据文件：`/Users/litiezhu/workspace/github/milvus-data/marten-docs.db`
- 当前 `Milvus` collection：`marten_docs_milvus`
- 当前 `Qdrant` collection：`marten-docs`
- 当前本地 embedding 模型：`/Users/litiezhu/workspace/github/models/bge-small-zh-v1.5`
