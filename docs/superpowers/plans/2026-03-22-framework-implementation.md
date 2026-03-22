# Framework Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four approved framework stages in `Marten` without drifting from the current control-plane-first architecture.

**Architecture:** Build thin public facades over the existing runtime/control-plane code, add config-driven endpoint routing with safe fallback to the current single-entry behavior, introduce a minimal retrieval capability that can be attached to builtin agents, then validate the reuse model with a standalone sample private project. Each stage must end with tests, document re-check, and a handoff update.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, unittest, JSON config, local sample workspace

---

## Chunk 1: Stage 1 Public Surface

### Task 1: Add failing tests for framework facade and builtin agent registry

**Files:**
- Create: `tests/test_framework_public_surface.py`
- Modify: `tests/test_runtime_components.py`
- Inspect: `app/core/config.py`
- Inspect: `app/runtime/agent_runtime.py`

- [ ] Step 1: Write failing tests for a public facade surface that resolves builtin agents and config-backed agent descriptors.
- [ ] Step 2: Run `python -m unittest tests.test_framework_public_surface -v` and confirm the new tests fail for missing modules or behaviors.
- [ ] Step 3: Implement minimal framework facade modules and builtin registry entry points.
- [ ] Step 4: Re-run `python -m unittest tests.test_framework_public_surface tests.test_runtime_components -v` and confirm green.

### Task 2: Add minimal stable framework modules

**Files:**
- Create: `app/framework/__init__.py`
- Create: `app/framework/facade.py`
- Create: `app/framework/builtin_agents.py`
- Modify: `app/runtime/agent_runtime.py`
- Modify: `app/core/config.py`

- [ ] Step 1: Add a stable facade object exposing config loading, runtime construction, and builtin agent resolution.
- [ ] Step 2: Add a builtin-agent registry/entry abstraction for `main-agent`, `ralph`, and `code-review-agent`.
- [ ] Step 3: Keep internal imports thin; do not move orchestration internals or persistence into the public layer.
- [ ] Step 4: Run targeted tests again and keep the public API minimal.

### Task 3: Stage 1 verification and docs sync

**Files:**
- Modify: `docs/internal/session-handoff.md`
- Inspect: `docs/architecture/framework-public-surface.md`
- Inspect: `docs/evolution/framework-implementation-plan.md`

- [ ] Step 1: Run `python -m unittest tests.test_framework_public_surface tests.test_runtime_components tests.test_mvp_e2e -v`.
- [ ] Step 2: Re-read the public-surface and implementation-plan docs to confirm the code still matches the approved boundary.
- [ ] Step 3: Update `docs/internal/session-handoff.md` with Stage 1 progress, test evidence, and next step.

## Chunk 2: Stage 2 Multi-Endpoint Routing

### Task 4: Add failing routing tests

**Files:**
- Modify: `tests/test_gateway.py`
- Create: `tests/test_channel_routing.py`
- Inspect: `app/control/gateway.py`
- Inspect: `app/control/routing.py`
- Inspect: `app/channel/feishu.py`

- [ ] Step 1: Write failing tests for endpoint config parsing, default agent/workflow binding, delivery routing, and fallback behavior.
- [ ] Step 2: Run `python -m unittest tests.test_channel_routing tests.test_gateway -v` and verify RED.
- [ ] Step 3: Implement endpoint models and config-driven route resolution with backward-compatible defaults.
- [ ] Step 4: Re-run the routing test suite and keep the previous single-endpoint path green.

### Task 5: Add endpoint routing modules

**Files:**
- Create: `app/channel/endpoints.py`
- Modify: `app/core/config.py`
- Modify: `app/control/routing.py`
- Modify: `app/control/gateway.py`
- Modify: `app/models/schemas.py`

- [ ] Step 1: Introduce `ChannelEndpoint`, `EndpointBinding`, and `ConversationRoute` models.
- [ ] Step 2: Parse endpoint and delivery-policy config from `platform.json` with default fallback to `main-agent`.
- [ ] Step 3: Thread endpoint routing state into gateway session payloads without breaking current tests.
- [ ] Step 4: Add minimal delivery-endpoint fallback behavior and explicit routing failures for invalid handoff.

### Task 6: Stage 2 verification and docs sync

**Files:**
- Modify: `docs/internal/session-handoff.md`
- Inspect: `docs/architecture/multi-endpoint-channel-routing.md`
- Inspect: `docs/evolution/framework-implementation-plan.md`

- [ ] Step 1: Run `python -m unittest tests.test_channel_routing tests.test_gateway tests.test_mvp_e2e -v`.
- [ ] Step 2: Re-read the routing spec and implementation plan to confirm no drift toward complex routing DSL or admin surfaces.
- [ ] Step 3: Update `docs/internal/session-handoff.md` with Stage 2 progress, evidence, and Stage 3 entry conditions.

## Chunk 3: Stage 3 RAG Capability MVP

### Task 7: Add failing retrieval tests

**Files:**
- Create: `tests/test_rag_capability.py`
- Modify: `tests/test_runtime_components.py`
- Inspect: `app/runtime/agent_runtime.py`

- [ ] Step 1: Write failing tests for retrieval provider registration, knowledge-domain config, retrieval policy resolution, and context merge into agent prompts.
- [ ] Step 2: Run `python -m unittest tests.test_rag_capability -v` and verify RED.
- [ ] Step 3: Implement the minimal retrieval capability and prompt merge hook.
- [ ] Step 4: Re-run `python -m unittest tests.test_rag_capability tests.test_runtime_components -v` and verify GREEN.

### Task 8: Add retrieval capability modules

**Files:**
- Create: `app/rag/__init__.py`
- Create: `app/rag/retrieval.py`
- Create: `app/rag/facade.py`
- Modify: `app/core/config.py`
- Modify: `app/runtime/agent_runtime.py`

- [ ] Step 1: Add `KnowledgeDomain`, `RetrievalPolicy`, `ContextMergePolicy`, and retrieval provider protocol.
- [ ] Step 2: Add config parsing for domains/policies with builtin-safe defaults.
- [ ] Step 3: Merge retrieval context into agent system prompts in a bounded, optional way.
- [ ] Step 4: Keep RAG optional and capability-only; do not add knowledge storage to the framework.

### Task 9: Stage 3 verification and docs sync

**Files:**
- Modify: `docs/internal/session-handoff.md`
- Inspect: `docs/architecture/rag-capability-mvp.md`
- Inspect: `docs/evolution/framework-implementation-plan.md`

- [ ] Step 1: Run `python -m unittest tests.test_rag_capability tests.test_runtime_components tests.test_mvp_e2e -v`.
- [ ] Step 2: Re-read the RAG MVP spec and confirm the implementation remains capability-only.
- [ ] Step 3: Update `docs/internal/session-handoff.md` with Stage 3 completion evidence and Stage 4 verification scope.

## Chunk 4: Stage 4 Minimal Private Project Validation

### Task 10: Add a standalone sample private project

**Files:**
- Create: `examples/private_agent_suite/README.md`
- Create: `examples/private_agent_suite/agents.json`
- Create: `examples/private_agent_suite/platform.json`
- Create: `examples/private_agent_suite/models.json.example`
- Create: `examples/private_agent_suite/mcp.json.example`
- Create: `examples/private_agent_suite/skills/README.md`
- Create: `examples/private_agent_suite/private_docs/README.md`
- Create: `tests/test_private_project_example.py`

- [ ] Step 1: Write a failing validation test that the sample private project can resolve builtin agents, endpoint bindings, and private retrieval domains without importing internal-only modules.
- [ ] Step 2: Run `python -m unittest tests.test_private_project_example -v` and verify RED.
- [ ] Step 3: Add a minimal sample project using only public surface and supported extension config.
- [ ] Step 4: Re-run the private-project validation tests and verify GREEN.

### Task 11: Final verification and handoff update

**Files:**
- Modify: `docs/internal/session-handoff.md`
- Inspect: `docs/internal/session-handoff.md`
- Inspect: `docs/README.md`
- Inspect: `docs/evolution/framework-implementation-plan.md`

- [ ] Step 1: Run `python -m unittest discover -s tests -v`.
- [ ] Step 2: If environment is configured, run `python -m unittest tests.test_live_chain -v`; otherwise record that it was intentionally skipped and why.
- [ ] Step 3: Re-read the core docs and confirm the repo still matches: stable framework, builtin agents preserved, multi-endpoint enabled, RAG capability-only, private logic out of core.
- [ ] Step 4: Update `docs/internal/session-handoff.md` with final stage progress, evidence, branch, and remaining risks if any.
