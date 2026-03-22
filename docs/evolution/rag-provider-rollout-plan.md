# RAG Provider Rollout Plan

> 更新时间：2026-03-23
> 文档角色：`docs/evolution` 下的当前 rollout 文档
> 目标：把 `Marten` 的 RAG capability 从最小原型推进到统一 provider surface，并为多向量库接入留出稳定扩展点。

## 一、目标状态

完成后，`Marten` 应具备下面这些特征：

- 调用方只依赖统一 retrieval contract
- `RAGFacade` 统一请求处理、后处理和 merge
- 新增向量库时只需要增加 provider adapter
- 当前先用 `Qdrant` 跑通，后续可扩展到 `Milvus`

## 二、范围

本轮关注：

- request / response / result shape 收口
- provider registry
- post-processing pipeline
- `Qdrant` first 的落地顺序
- `Milvus` 真实接入与后续远端部署切换边界

本轮不做：

- 重型知识平台
- 完整索引管理后台
- 所有 provider 的一次性接入

## 三、分阶段推进

### Stage 1: Surface 收口

目标：

- 定义统一 request / response / result contract
- 保持 `InMemoryRetrievalProvider` 作为测试基线

### Stage 2: Provider Adapter 化

目标：

- provider 只负责 search / fetch
- 把去重、merge、citation、budgeting 从 provider 中抽出来

### Stage 3: Qdrant First

目标：

- 接入 `Qdrant` adapter
- 跑通 `Operational RAG`

### Stage 4: Milvus Runtime

目标：

- 明确 `Milvus` adapter 的输入输出要求
- 本地 `Milvus Lite` 已接通并跑通真实 `search / fetch`
- 后续切远端 `Milvus` 时仍不改 facade contract

## 四、验收标准

当下面条件成立时，说明 RAG provider 文档工作完成：

1. `architecture/rag-provider-surface.md` 已成为当前正式规格
2. 调用面不再围绕具体向量库写文档
3. 后续实现 agent 可以按 plan 独立接入 `Qdrant`
4. 后续实现 agent 可以在不改调用 contract 的前提下接 `Milvus`
5. 当前已经有可运行的本地 `Milvus Lite` 路径，后续只需补远端部署切换说明

## 五、后续实现的强约束

- `RAGFacade` 是调用面真相，不是具体 provider
- provider adapter 只负责 backend-specific 行为
- 后处理必须统一
- embedding 与 provider 必须解耦
