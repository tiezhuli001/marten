## Goal

检查 `docs/evolution` 对应实现是否完整，必要时修复并验证；并完成一轮完整测试，确认服务达到可用阶段。

## Baseline

- `docs/evolution/`
- `docs/archive/status/STATUS.md`（路径不存在，已确认）

## Done Criteria

- 读完 evolution 与关联 architecture 文档
- 核对实现与测试覆盖
- 修复安全且在范围内的缺口
- 跑相关验证并记录结果
- 跑完整测试轮并确认关键链路可用

## Done

- 读取 `docs/evolution` 三份文档与四份关联 architecture 文档
- 确认仓库内不存在用户给定的 `docs/archive/status/STATUS.md`
- 识别出当前实现已覆盖 public surface / multi-endpoint / RAG 的基础骨架
- 跑通现有针对性测试：`python3 -m unittest tests.test_framework_public_surface tests.test_channel_routing tests.test_rag_capability tests.test_private_project_example`
- 建立工作分支 `codex/evolution-implementation-audit`
- 新增回归测试，锁定两个文档缺口：
- `MartenFramework` 缺少稳定 facade 收口
- `allowed_handoffs` 未阻止显式 handoff，且未记录 routing failure
- 补齐 `MartenFramework` 对 channel/session/context/task/runtime/rag 的公开入口
- 在 gateway routing 中执行 `allowed_handoffs`，对被拒绝的显式 `@ralph` 回退到默认路由并记录 `routing_failure` 事件
- 跑通扩展后的回归集合：`python3 -m unittest tests.test_framework_public_surface tests.test_gateway tests.test_channel_routing tests.test_rag_capability tests.test_private_project_example tests.test_mvp_e2e`
- 按仓库推荐入口跑完整测试轮：`python3 -m unittest discover -s tests -v`
- 在当前配置下，`live_test.enabled=true`，完整测试轮包含 `tests.test_live_chain` 在内并通过
- 修复 live chain 暴露出的 LLM timeout 缺口：`TimeoutError` 现在会进入统一重试路径
- 新增回归测试：`tests.test_llm_runtime.SharedLLMRuntimeTests.test_generate_retries_timeout_errors_with_exponential_backoff`
- 重新跑完整测试轮，最新结果提升为 147 tests 全绿

## In Progress

- 无

## Next

- 如需继续提高上线把握度，可补一轮手动 smoke run / API 启动验证
- 如需合并，可继续做代码评审或提交整理

## Blockers

- `pytest` 本地不可用，需改用 `python3 -m unittest`
- 用户给定状态文件路径不存在

## Verification

- `python3 -m unittest tests.test_framework_public_surface tests.test_channel_routing tests.test_rag_capability tests.test_private_project_example` -> PASS
- `pytest -q tests/test_framework_public_surface.py tests/test_channel_routing.py tests/test_rag_capability.py tests/test_private_project_example.py` -> FAIL (`pytest: command not found`)
- `python3 -m unittest tests.test_framework_public_surface tests.test_gateway` -> PASS
- `python3 -m unittest tests.test_framework_public_surface tests.test_gateway tests.test_channel_routing tests.test_rag_capability tests.test_private_project_example tests.test_mvp_e2e` -> PASS
- `python3 -m unittest tests.test_llm_runtime.SharedLLMRuntimeTests.test_generate_retries_timeout_errors_with_exponential_backoff -v` -> PASS
- `python3 -m unittest tests.test_llm_runtime -v` -> PASS (`Ran 17 tests ... OK`)
- `python3 -m unittest tests.test_live_chain -v` -> PASS (`Ran 1 test in 89.508s ... OK`)
- `python3 -m unittest discover -s tests -v` -> PASS (`Ran 147 tests in 96.170s`, includes live configuration path because `platform.json` has `live_test.enabled=true`)
