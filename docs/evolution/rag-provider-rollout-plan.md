# RAG Provider Rollout Plan

> 更新时间：2026-03-26
> 文档角色：`docs/evolution` 下的演进约束文档
> 当前状态：本轮“RAG 最小保留面收口”已完成，后续只保留扩展规则，不再有仓内待执行 chunk。

## 本轮结果

截至当前仓库状态，RAG rollout 已收口到下面的完成态：

- 调用方统一依赖 `RAGFacade`
- retrieval request / response / merge policy 已固定为当前 contract
- 仓库内具体 provider 实现已删除
- 仅保留 `InMemoryRetrievalProvider` 作为示例与测试基线
- `indexing.py` 保留为 manual-only 的辅助能力，不进入默认主链回归

## 当前保留面

当前允许继续演进的只有三块：

1. facade contract
   - `RAGFacade`
   - `RetrievalRequest` / `RetrievalResponse`
   - policy / merge 边界
2. runtime integration point
   - retrieval context 如何进入 agent runtime
3. manual indexing helper
   - markdown chunking
   - manifest sync

## 当前不做

下面这些内容不再是当前仓库默认职责：

- 多 provider 同时铺开
- vector store collection lifecycle
- 重型知识平台或索引后台
- 让 agent prompt 直接绑定具体向量库实现

## 后续新增 provider 的约束

如果未来真的要接入具体向量库，必须同时满足：

1. 新增需求来自真实业务，而不是“也许以后会用”
2. 一次只引入单个最小 provider
3. 调用 contract 不改，仍由 `RAGFacade` 抽象底层差异
4. 新增测试优先落在 `manual` 或 targeted contract，不恢复大体量 provider matrix
