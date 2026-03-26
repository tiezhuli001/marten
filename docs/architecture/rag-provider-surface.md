# RAG Provider Surface

> 更新时间：2026-03-26
> 文档角色：`docs/architecture` 下的当前实现规格
> 目标：把 `Marten` 保留的 RAG 能力收口成最小 retrieval surface，不让未来扩展反向膨胀当前主链复杂度。

## 当前结论

`Marten` 当前不再把“多向量库 provider 适配层”当作主仓库默认代码面。

当前仓库只保留下面这组最小真相：

- 调用方统一走 `RAGFacade`
- request / response / document shape 统一走 retrieval contract
- runtime 只依赖 policy / merge boundary，不依赖具体 provider 细节
- 仓库内仅保留 `InMemoryRetrievalProvider` 作为最小示例与测试基线
- `app/rag/indexing.py` 只保留 markdown chunking / manifest sync 的基础辅助能力，归 `manual` suite 守面

也就是说：

> 具体向量库接入属于后续真实需求的扩展，不是当前 self-host 主链的默认承诺。

## 当前代码面

截至 `2026-03-26`，`app/rag/` 只剩 3 个文件、`465` 行 Python：

1. `retrieval.py`
   - `RAGFacade`
   - `RetrievalRequest` / `RetrievalResponse`
   - `RetrievalPolicy` / `ContextMergePolicy`
   - `InMemoryRetrievalProvider`
2. `indexing.py`
   - markdown chunk collection
   - stable item id / content hash
   - manifest sync plan
3. `__init__.py`
   - 最小公开导出

已删除：

- `app/rag/providers/__init__.py`
- `app/rag/providers/milvus.py`
- `app/rag/providers/qdrant.py`

## 主链依赖边界

当前主链只依赖下面两类入口：

1. retrieval contract
   - agent runtime 可以根据 policy 取回文档上下文
   - 调用方不需要感知底层 provider
2. runtime merge integration
   - 是否注入 retrieval context，由 policy 决定
   - 去重与 top-k 裁剪在 facade 内完成

主链当前不依赖：

- provider-specific search 参数
- collection lifecycle
- upsert/delete runtime
- server-side rerank
- 多 backend 并存策略

## 测试与回归策略

当前保留的测试边界：

- `tests.test_rag_capability`
  - 留在 `quick` / `regression`
  - 只守两件事：
    - facade 检索与去重 contract
    - runtime 在 `trigger_mode=always` 下正确合并 retrieval context
- `tests.test_rag_indexing`
  - 留在 `manual`
  - 只守 markdown chunking 与 manifest sync helper

这意味着 RAG 仍被保留，但不再以“大而全 provider surface + 大体量测试”形态存在。

## 后续扩展规则

只有当真实产品需求出现时，才允许重新引入具体 provider adapter。届时必须满足：

1. 调用方 contract 不变，仍只依赖 `RAGFacade`
2. 新增实现必须是单个最小 provider，而不是一次性恢复多 backend 铺面
3. provider-specific 能力不能泄漏到 agent prompt 或 runtime 主链
4. 如需更重的 indexing / sync 工具，优先放在 manual 或独立运维路径，不进入默认回归
