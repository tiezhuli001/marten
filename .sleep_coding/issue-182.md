# Ralph Task

- task_id: c0998683-095a-41fb-a79b-485f55e8c1a4
- issue_number: 182
- branch: codex/issue-182-sleep-coding

# Issue: Task 10 - Add a standalone sample private project

## Context
Per the implementation plan, create a sample private agent suite demonstrating the public surface for builtin agents, endpoint bindings, and private retrieval domains.

## Implementation Approach

### Step 1: Create validation test
Create `tests/test_private_project_example.py` with tests that verify:
- Sample project can resolve builtin agents
- Sample project can configure endpoint bindings  
- Sample project can define private retrieval domains
- No internal-only modules are imported

### Step 2: Create sample project structure
Create `examples/private_agent_suite/` with:
- `README.md` - Project documentation
- `agents.json` - Agent configuration using public schema
- `platform.json` - Platform configuration
- `models.json.example` - Model configuration template
- `mcp.json.example` - MCP server configuration template
- `skills/README.md` - Skills documentation
- `private_docs/README.md` - Private documentation

## Risks
- Public API surface must be verified against actual codebase
- Configuration schemas need validation against implementation

## Validation
Run: `python -m unittest tests.test_private_project_example -v`
