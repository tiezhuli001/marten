# Live Chain Failure Semantics

> 更新时间：2026-03-25
> 文档角色：真实链路失败语义、runtime capability 边界与并发真相说明

## 一、目的

本文件定义 `Marten` 真实链路在 2026-03-25 阶段的三类正式边界：

- 失败时系统应该如何暴露真实原因
- 各 workflow 到底有没有真实 tool-call runtime capability
- 单机 self-host 模式下当前并发控制各层分别承担什么责任

目标不是“让 live 更容易通过”，而是让失败、重试、恢复和 operator 介入都基于真实证据。

## 二、正式失败语义

### 1. transport retry

- 只适用于 provider / network / transport 层短时抖动
- 必须由底层 runtime 明确控制次数、延迟和最终超时
- retry 耗尽后必须抛出真实错误，不自动改写成成功

### 2. agent runtime failure

- `main-agent`、`ralph`、`code-review-agent` 的关键主链步骤失败时，默认显式失败
- 不把 provider 失败、上下文失败或 capability 缺失静默转成 heuristic success
- operator 应能看到阶段、原始错误和恢复入口

### 3. structured output failure

- parse failure 不是“模型基本成功”
- 必须保留原始输出摘要、provider/model 和 parse error
- 需要时进入 `needs_attention` 或上抛给控制面处理

### 4. delivery failure

- 通知发送状态不等于主链成功
- final delivery 仍以 review truth、validation evidence 和 task state 为准

## 三、当前 runtime capability matrix

| Workflow | Agent | 当前能力边界 | 是否有真实 tool-call loop | 正式输出边界 |
| --- | --- | --- | --- | --- |
| `default` | `main-agent` | 可使用 MCP 能力做外部操作 | 否，当前这条 structured path 仍是单次生成 | 结构化 handoff / issue draft |
| `sleep_coding` plan | `ralph` | 生成 plan | 否 | 结构化 plan object |
| `sleep_coding` execution | `ralph` | 生成 execution draft / artifact contract | 否 | 结构化 execution draft |
| `code_review` | `code-review-agent` | 生成 findings / review markdown | 否 | 结构化 review object |

补充：

- 当前 `generate_structured_output()` 只负责一次模型生成，不负责 tool-call roundtrip
- 因此对 `sleep_coding` 和 `code_review`，prompt 不能把 MCP tool catalog 当成“本步骤可真实执行的能力”暴露给模型
- 如果未来要让这些 workflow 真正自主决定是否调用工具，必须先实现真实 tool-call loop，而不是只改 prompt 文案

## 四、为什么当前 structured workflow 不暴露工具目录

这不是“agent 不应该自己判断是否用工具”，而是当前 runtime 能力边界如此：

- 该 workflow 走的是单次 structured output path
- runtime 不会消费模型发起的 tool calls
- 如果仍把工具目录暴露给模型，只会制造伪工具调用、命令文本或无效 JSON

所以当前正式语义应表述为：

- 这些 workflow 运行在 **artifact / structured-output boundary**
- 不是通用 interactive tool-calling boundary

这和调研文档中的多数开源实现一致：子 agent 更常见的是独立完成本地工作，再把结果 artifact / 摘要返给主链，而不是把整条认知过程都编码成严格 RPC。

## 四点五、当前 `structured_output.py` 的正式角色

当前 `app/runtime/structured_output.py` 的角色应视为：

- **边界宽容解析器**
- 不是主链强保证协议解析器

它当前负责的是：

- 尝试从模型输出中提取对象
- 兼容少量噪声包装，例如 think-text、外围 prose、hash-rocket 风格对象

它当前不负责的是：

- 代替 workflow schema validation
- 把宽容解析误写成“协议已经可靠成立”

因此当前正式边界是：

- `structured_output.py` 可以宽容提取 candidate object
- 各 workflow 仍必须在上层做 `model_validate`
- 关键路径失败与否，由上层 schema / runtime failure semantics 决定，而不是由 parser 是否“勉强提取出对象”决定

如果未来要进一步收紧：

- 应把“宽容边界提取”和“严格协议解析”拆成两个明确角色
- 不应在本轮 live-chain 纠偏里直接混做

### 当前 `parse_structured_object()` call-site matrix

| 调用点 | 宽容提取是否允许 | 上层 schema / normalization | 失败策略 |
| --- | --- | --- | --- |
| `main_agent._parse_issue_draft_output()` | 是 | `_normalize_main_agent_output()` / `MainAgentCodingHandoff` 归一化 | `intake` 边界允许回退到 heuristic draft，不作为 fail-closed 主链步骤 |
| `RalphDraftingService._parse_plan_output()` | 是 | `SleepCodingPlan.model_validate()` | schema 不合法时回退到 heuristic plan；planning 边界仍不把 parser 成功视为协议成功 |
| `RalphRuntimeExecutor._parse_execution_output()` | 是 | `SleepCodingExecutionDraft.model_validate()` | fail-closed；重试后仍不合法则抛错并写 `execution_failure_evidence` |
| `RuntimeReviewer.parse_response()` | 是 | `ReviewSkillOutput.model_validate()` | fail-closed；抛错并写 `review_failure_evidence` |

当前结论：

- `parse_structured_object()` 只负责“尽量把 candidate object 提出来”
- 真正决定 workflow 是否成立的，是调用点后续的 schema validation 与 failure semantics
- 2026-03-25 这一轮不新增 strict parser，因为当前真正需要 fail-closed 的 execution / review 路径已经在上层显式 `model_validate`

## 五、A2A / 开源参考结论

参考：

- `/Users/litiezhu/docs/ytsd/工作学习/AI学习/agent/Agent-to-Agent通信模式深度调研报告.md`

当前对 `Marten` 最有价值的结论是：

- 优秀项目通常让子 agent 自己完成工具调用，不把工具调用细节回传主 agent
- 主 agent 接的是最终结果、摘要或事件，不是每一步内部思考状态
- 如果没有真实 A2A/tool runtime，就不要把普通 artifact exchange 伪装成强保证协议

因此 `Marten` 当前更合理的方向是：

- 保持 `handoff`、`coding_artifact`、`review machine_output/human_output` 这些稳定 contract
- 把真正可执行的 tool runtime 和 artifact-only workflow 区分开

## 六、当前并发控制 inventory

### 1. 入口层 `threading.Lock`

位置：

- `app/control/gateway.py`

职责：

- 序列化同一 session 的并发入口请求
- 避免同一条 session 在线程并发下同时命中 dedupe / routing / intake 分支

### 2. SQLite `execution_lanes`

位置：

- `app/control/session_registry.py`

职责：

- 作为单机 self-host 的跨请求单活真相
- 记录 active task 和 queued tasks

### 3. worker claim lease

位置：

- `app/control/sleep_coding_worker.py`
- `app/control/sleep_coding_worker_store.py`

职责：

- 保护 issue poll / claim / retry / heartbeat 生命周期
- 防止 worker 重复消费同一 issue

## 七、当前并发控制的审计结论

截至本轮，三层并发控制并不完全重复：

- `threading.Lock` 保护的是同 session 入口串行化与 dedupe 时序
- `execution_lanes` 保护的是主链单活 truth
- claim lease 保护的是 worker 消费语义

补充的行为证据：

- `execution_lane` 对同一 queued task 的重复 acquire 需要保持幂等，不能重复堆积 queued truth
- worker claim 在 lane 被其他任务占用时只能保持 `queued`，lane 释放后才能继续 claim 并启动任务
- 因此 `execution_lane` 和 claim lease 不是同一层状态的两份副本；前者管主链单活，后者管 issue 轮询与 lease 生命周期

因此在没有额外 harness 证明之前，不应直接删除其中一层，只因为它“看起来像重复锁”。

后续若要做减法，推荐顺序是：

1. 先补并发 harness，证明删掉某一层后：
   - 不会双开主任务
   - 不会丢失 dedupe
   - 不会破坏 queued/busy truth
2. 再逐层尝试删除或收敛

## 八、当前 operator 需要看到的失败证据

对 execution / review 失败，至少需要保留：

- `stage`
- `provider`
- `model`
- `parse_error` 或原始异常
- `raw_output_excerpt`
- `last_error`

这保证 live 失败时可以先定位根因，而不是继续加 fallback。
