# Structured Output Role Follow-up Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 明确并收敛 `structured_output` 的职责边界，把“宽容边界提取”和“严格协议解析”分开表达。

**Architecture:** 当前 `parse_structured_object()` 继续作为边界宽容解析器保留，用于从噪声模型输出中提取 candidate object。后续若需要更强协议保证，应新增严格解析层，而不是继续把同一个 helper 同时当容错提取器和协议验证器使用。

**Tech Stack:** Python 3.11+, unittest, Pydantic schema validation, builtin agents.

## Execution Result

> 更新时间：2026-03-25
> 执行结论：本 follow-up 已完成到“call-site 边界写清、容错提取测试保留、真正 fail-closed 的路径继续由上层 schema validation 负责”的目标；本轮不新增 strict parser。

- 已完成 parser call-site inventory，并同步进 `docs/architecture/live-chain-failure-semantics.md`
- 已补 parser-role 相关测试：
  - `tests.test_main_agent` 现在覆盖 think-text 与 hash-rocket 包装的 issue draft
  - `tests.test_sleep_coding` 现在覆盖：
    - think-text / hash-rocket plan 提取
    - 提取成功但 plan schema 不合法时回退 heuristic plan
    - 提取成功但 execution schema 不合法时 fail-closed 并写 `execution_failure_evidence`
  - `tests.test_review` 已继续覆盖：提取成功但 review schema 不合法时 fail-closed 并写 `review_failure_evidence`
- 当前结论：
  - `main-agent` intake 是容错入口，允许 heuristic fallback
  - `sleep_coding` plan 是容错 planning boundary，允许 heuristic fallback
  - `sleep_coding` execution / `code_review` 是关键主链步骤，继续 fail-closed
- 本轮不新增 `strict_structured_output.py`：
  - 当前需要强协议保证的 workflow 已通过 `model_validate` + failure evidence 达成，不需要再引入第二套解析 helper
- 最新验证：
  - `python -m unittest tests.test_main_agent tests.test_sleep_coding tests.test_review tests.test_session_registry tests.test_sleep_coding_worker -v`
    - PASS (`Ran 99 tests in 3.536s`)
  - `python scripts/run_test_suites.py quick`
    - PASS (`Ran 132 tests in 9.063s`)

---

## Chunk 1: Freeze Parser Roles

### Task 1.1: Inventory all current parser call sites

**Files:**
- Inspect: `app/runtime/structured_output.py`
- Inspect: `app/agents/main_agent/application.py`
- Inspect: `app/agents/ralph/drafting.py`
- Inspect: `app/agents/ralph/runtime_executor.py`
- Inspect: `app/agents/code_review_agent/runtime_reviewer.py`

- [x] Step 1: 列出所有 `parse_structured_object()` 调用点。
- [x] Step 2: 对每个调用点标注：
  - 是否允许宽容解析
  - 后续是否还有 schema validation
  - 失败时是否会 fail-closed
- [x] Step 3: 输出一份 call-site matrix，作为后续实现依据。

### Task 1.2: Lock parser policy in tests

**Files:**
- Modify or add: `tests/test_main_agent.py`
- Modify or add: `tests/test_sleep_coding.py`
- Modify or add: `tests/test_review.py`
- Add if needed: `tests/test_structured_output.py`

- [x] Step 1: 保留并整理“宽容提取仍允许”的测试：
  - think-text 包裹 JSON
  - hash-rocket 风格对象
- [x] Step 2: 增加“上层仍必须 fail-closed”的测试：
  - 提取成功但 schema 不合法时必须失败
  - execution / review 失败时必须保留 evidence
- [x] Step 3: Run:
  - `python -m unittest tests.test_main_agent tests.test_sleep_coding tests.test_review -v`

## Chunk 2: Split Strict Parsing Only If Needed

### Task 2.1: Decide whether a strict parser is necessary

**Files:**
- Modify if needed: `app/runtime/structured_output.py`
- Add if needed: `app/runtime/strict_structured_output.py`

- [x] Step 1: 只有在某个 workflow 明确需要强协议保证时，才新增 strict parser。
- [x] Step 2: 若新增 strict parser，禁止对当前宽容 helper 做 silent broadening。
- [x] Step 3: 每个 strict workflow 都必须显式声明为何不能继续使用宽容边界解析。

### Task 2.2: Verify no protocol drift

**Files:**
- Modify if needed: `docs/architecture/live-chain-failure-semantics.md`
- Modify if needed: `STATUS.md`

- [x] Step 1: 同步文档口径，明确 tolerant extractor 和 strict parser 的职责分界。
- [x] Step 2: Run:
  - `python scripts/run_test_suites.py quick`
