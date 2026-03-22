## Goal

在统一 `RAGFacade` / provider surface 不变的前提下，补齐真实 `Milvus` 接入，并把文档索引推进到具备最小可用的增量同步与 collection schema 管理。

## Baseline

- `docs/architecture/rag-provider-surface.md`
- `docs/evolution/rag-provider-rollout-plan.md`
- `docs/plans/2026-03-22-rag-provider-surface-rollout.md`
- `platform.json`

## Done Criteria

- 真实 `Milvus` provider 接入完成，不改 `RAGFacade` 调用面
- `search/fetch` 映射通过测试与真实 smoke test
- `platform.json` 可装配 `Milvus` provider
- `docs/` 语料成功写入本地 `Milvus`
- 文档索引具备最小增量同步与 schema 守卫
- 相关单元测试通过
- 完成一轮目标偏移检查
- `STATUS.md` 与当前状态一致

## Done

- 完成 agent system / RAG provider 文档重构，当前主入口已收口到 `docs/architecture/*`、`docs/evolution/*`、`docs/plans/*`
- 收紧 `agents/main-agent/AGENTS.md`、`agents/ralph/AGENTS.md`、`agents/code-review-agent/AGENTS.md`，与新的 runtime contracts 对齐
- 升级 `app/rag/retrieval.py`，形成统一 `RetrievalRequest` / `RetrievedDocument` / `RetrievalResponse` surface，并支持按 `platform.json` 自动注册 provider
- 新增 `app/rag/providers/qdrant.py` 与 `app/rag/providers/milvus.py`，保持 facade contract 不变
- 更新 `app/rag/__init__.py`，导出新的 retrieval surface
- 在 `platform.json` 与 `platform.json.example` 中加入真实 Qdrant RAG 配置，覆盖 `main-agent`、`ralph`、`code-review-agent`
- 新增 `scripts/index_docs_to_qdrant.py`
- 在 `platform.json` 与 `platform.json.example` 中加入 `local-milvus` provider 与 `repo-docs-milvus` domain 配置
- 新增 `scripts/index_docs_to_milvus.py`
- 新增共享索引模块 `app/rag/indexing.py`
- 创建本地数据目录 `/Users/litiezhu/workspace/github/qdrant-data`
- 创建本地模型目录 `/Users/litiezhu/workspace/github/models`
- 创建本地 `Milvus Lite` 数据目录 `/Users/litiezhu/workspace/github/milvus-data`
- 拉起本地 Qdrant 容器 `marten-qdrant`，监听 `http://127.0.0.1:6333`
- 下载本地模型到 `/Users/litiezhu/workspace/github/models/bge-small-zh-v1.5`
- 使用 `docs/**/*.md` 完成首轮索引，写入 collection `marten-docs`
- 安装 `pymilvus` 与 `milvus-lite`
- 真实接入 `MilvusRetrievalProvider`：
- 支持 `uri` / `token` / `db_name` / `vector_field` / `primary_field` / `search_params` / 本地 embedding 配置
- 使用 `pymilvus` 连接与 collection API 完成真实 `search/fetch`
- 支持从 `domain.metadata["collection_name"]` 解析实际 collection
- `item_ref` 统一为 `{collection}:{id}`
- 强化 `tests/test_rag_capability.py`：
- 覆盖 `Milvus` 的 `search/fetch` 映射
- 覆盖 `RAGFacade` 从 `platform.json` 装配 `MilvusRetrievalProvider`
- 新增 `tests/test_rag_indexing.py`
- 覆盖 markdown chunk 稳定切片、重复标题唯一 ID、增量同步计划
- 为 `Qdrant` / `Milvus` 索引脚本补充最小 schema 守卫与 manifest 驱动的增量同步
- 修复索引主键稳定性 bug：同文件重复标题 chunk 现在使用 occurrence 参与 stable id，避免 manifest 冲突导致每轮重复 upsert
- 验证 `Qdrant` 与 `Milvus` 第二轮索引都可收敛到 `0 upserts / 0 deletes`
- 完成一轮目标偏移检查：本轮实现仍然围绕统一 provider surface；`Milvus` 只是新增 provider 实现与本地索引能力，没有改 `RAGFacade` 调用 contract
- 修复 `QdrantRetrievalProvider` 的真实运行时问题：
- 改为优先使用显式 `query_points` 检索，避免误走 `qdrant-client` 的隐式 embedding / `fastembed` 路径
- 保留旧 `query()` 仅作为兼容 fallback
- 强化 `tests/test_rag_capability.py`，覆盖“client 同时暴露 `query` 和 `query_points` 时必须优先走 `query_points`”
- 清理 `requirements.txt` 中重复的 `tiktoken` 依赖项
- 完成目标偏移检查：实现仍然符合统一 provider surface 设计，没有把调用面耦合到具体向量库 SDK

## In Progress

- 无

## Next

- 如需继续深化，可把 `Milvus Lite` 本地模式和远端 `Milvus Standalone/Distributed` 配置切换补成更明确的运行手册
- 如需继续深化，可补充 provider 级 filter compatibility、rerank、observability 指标

## Blockers

- 无

## Verification

- `docker ps --filter name=marten-qdrant --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'` -> PASS（`marten-qdrant` 运行中，`6333` 已映射）
- `curl http://127.0.0.1:6333/collections` -> PASS（返回 `marten-docs` collection）
- `python scripts/index_docs_to_qdrant.py` -> PASS（首轮入库成功，随后稳定到 `chunks_upserted=0`, `chunks_deleted=0`, `chunks_unchanged=413`）
- `python scripts/index_docs_to_milvus.py` -> PASS（首轮入库成功，随后稳定到 `chunks_upserted=0`, `chunks_deleted=0`, `chunks_unchanged=413`）
- `python - <<'PY' ... RAGFacade(...).retrieve_response(agent_id='main-agent', workflow='general', query='主链路 main agent ralph code review final delivery') ... PY` -> PASS（`provider=qdrant`, `count=4`）
- `python - <<'PY' ... for agent_id in ['main-agent', 'ralph', 'code-review-agent'] ... retrieve_response(...) ... PY` -> PASS（三个 agent 都命中 `qdrant`, 各返回 `4` 条结果）
- `python - <<'PY' ... repo-docs-milvus policy ... RAGFacade(...).retrieve_response(...) ... fetched=... PY` -> PASS（`provider=milvus`, `count=4`, `fetch` 正常）
- `python -m unittest tests.test_rag_indexing tests.test_rag_capability tests.test_runtime_components tests.test_framework_public_surface tests.test_automation -v` -> PASS（`Ran 43 tests in 6.749s ... OK`）
- `rg -n "Qdrant|Milvus|provider surface|main-agent|ralph|code-review-agent|collection_name|retrieve_response" docs/architecture docs/plans docs/evolution -g '*.md'` -> PASS（文档与实现焦点一致）
