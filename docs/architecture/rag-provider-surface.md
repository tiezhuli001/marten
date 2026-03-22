# RAG Provider Surface

> 更新时间：2026-03-22
> 文档角色：`docs/architecture` 下的实现规格文档
> 目标：把 `Marten` 当前的 RAG capability 收口为统一 provider surface，使后续接入 Qdrant、Milvus 等向量库时不需要改调用方 contract。

## 一、设计结论

`Marten` 的 RAG 不应围绕某一个向量库写死。

当前正确边界应是：

- 检索请求统一进入 `RAGFacade`
- facade 面向统一的 retrieval request / response contract
- 各向量库只实现 provider adapter
- 后处理、去重、引用、merge policy 由框架统一处理

也就是说：

> Qdrant、Milvus、pgvector 等都只是 provider implementation，不是框架调用面的真相。

## 二、为什么要这样做

如果调用方直接依赖具体向量库，会马上出现三个问题：

1. agent 和 runtime 会被某个库的参数绑死
2. 后续换库或并存多库时，调用面会碎裂
3. 去重、rerank、citation、merge policy 会被复制到各 adapter 中

因此 `Marten` 应像 channel/provider adapter 一样，把 retrieval 也做成统一 surface。

## 三、正式分层

### 1. `RAGFacade`

职责：

- 接收统一 retrieval request
- 解析 policy / domain / merge policy
- 分发给 provider adapter
- 统一执行 post-processing
- 返回统一 retrieval response

### 2. `RetrievalProvider`

职责：

- 对接具体向量库或检索后端
- 执行 provider-native search / fetch
- 把结果映射成框架统一对象

### 3. `PostProcessor`

职责：

- dedupe
- top-k trimming
- optional rerank
- citation shaping
- context merge budgeting

### 4. `ContextMerge`

职责：

- 把 retrieval response 变成 agent runtime 可消费的上下文块

## 四、统一 request / response contract

### 1. `RetrievalRequest`

最小字段建议包括：

- `query`
- `agent_id`
- `workflow`
- `domains`
- `top_k`
- `filters`
- `query_mode`
- `include_citations`

短期内不要求每个 provider 都完整支持全部字段，但 request shape 应统一。

### 2. `RetrievedDocument`

最小字段建议包括：

- `item_ref`
- `domain_id`
- `title`
- `content`
- `source`
- `score`
- `metadata`

### 3. `RetrievalResponse`

最小字段建议包括：

- `provider`
- `results`
- `latency_ms`
- `truncated`
- `debug`

## 五、provider adapter contract

每个 provider adapter 至少需要实现：

- `search(request, domain) -> RetrievalResponse`
- `fetch(item_ref) -> RetrievedDocument | None`

可选能力可以通过 capability 声明，而不是塞进统一必选接口：

- hybrid search
- metadata filter
- server-side rerank
- upsert / delete
- collection lifecycle

## 六、统一后处理 contract

后处理不应散落在 provider adapter 中。

框架统一负责：

- dedupe by `item_ref`
- cross-domain merge
- token budgeting
- citation formatting
- merge policy

这样才能保证：

- 不同 provider 行为一致
- agent runtime 不需要知道底层库差异
- 新增 provider 只改 adapter，而不是全链路改一遍

## 七、当前推荐落地顺序

### Phase 1

- 保留现有 `InMemoryRetrievalProvider` 作为测试基线
- 把 request / response / result shape 补完整
- 引入 post-processing pipeline

### Phase 2

- 先接 `Qdrant` adapter
- 把 `Operational RAG` 跑通

### Phase 3

- 预留 `Milvus` adapter 接口
- 截至 `2026-03-23`，已接上本地 `Milvus Lite` 实例并跑通真实 `search/fetch`
- 远端 `Milvus Standalone / Distributed` 的部署与切换手册仍可后续补充

### Phase 4

- 按私有项目需要补 `pgvector` 或其他 provider

## 八、与 embedding 的边界

embedding model 选择与 vector store 选择应分开。

框架需要保证：

- provider surface 不绑定某个 embedding 模型
- retrieval request 不泄漏底层 embedding 实现细节
- 私有项目可按语料语言和成本自行切换 embedding

当前默认建议仍是：

- `Qdrant + nomic-embed-text`
- 中文语料为主时，`Qdrant + bge-small-zh-v1.5`

## 九、短期不做

- 不把 index 管理后台做进框架
- 不把向量库的 collection lifecycle 复杂化
- 不在当前阶段支持所有 provider 的全部高级特性
- 不让 agent prompt 直接面向具体向量库实现
