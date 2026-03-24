# Ralph Task

- task_id: 6b70bd78-b58b-45a3-98a3-ea72999af8df
- issue_number: 203
- branch: codex/issue-203-sleep-coding

# Private Project Example Implementation

## Context
Task 10 from the framework implementation plan requires adding a standalone sample private project that demonstrates resolution of builtin agents, endpoint bindings, and private retrieval domains without importing internal-only modules.

## Current State
No implementation exists. The task requires creating a sample project structure that uses only public surface APIs.

## Implementation Plan

### Step 1: Create sample project structure
Create `examples/private_agent_suite/` with:
- `README.md` - project documentation
- `agents.json` - agent definitions using public surface
- `platform.json` - platform configuration
- `models.json.example` - example model config
- `mcp.json.example` - example MCP config
- `skills/README.md` - skills documentation
- `private_docs/README.md` - private documentation

### Step 2: Create validation test
Create `tests/test_private_project_example.py` that verifies:
- Sample project can resolve builtin agents
- Sample project can resolve endpoint bindings
- Sample project can access private retrieval domains
- No internal-only modules are imported

### Key Design Decisions
- Use only public surface APIs from the framework
- Follow existing example patterns in the codebase
- Keep the sample minimal but functional

## Risks
- The exact public API surface needs verification against current codebase
- Test assertions may need adjustment based on actual framework capabilities

## Validation Path
1. Run `python -m pytest tests/test_private_project_example.py -v`
2. Verify RED (failing) initially
3. Implement sample project
4. Verify GREEN (passing) after implementation
