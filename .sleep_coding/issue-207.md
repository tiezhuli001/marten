# Ralph Task

- task_id: 7428b1a2-3a47-4731-9653-7c0d026a3371
- issue_number: 207
- branch: codex/issue-207-sleep-coding

# Issue: Task 10 - Add a standalone sample private project

## Context
Create a minimal sample private project in `examples/private_agent_suite/` that demonstrates the public surface of Marten without relying on internal-only modules.

## Implementation Plan

### Step 1: Explore Repository Structure
- Understand how Marten loads agents, endpoint bindings, and private retrieval domains
- Identify the public surface vs internal-only modules

### Step 2: Create Sample Project Structure
- `examples/private_agent_suite/README.md` - Overview
- `examples/private_agent_suite/agents.json` - Agent definitions
- `examples/private_agent_suite/platform.json` - Platform configuration
- `examples/private_agent_suite/models.json.example` - Model config example
- `examples/private_agent_suite/mcp.json.example` - MCP config example
- `examples/private_agent_suite/skills/README.md` - Skills documentation
- `examples/private_agent_suite/private_docs/README.md` - Private docs

### Step 3: Write Validation Test
Create `tests/test_private_project_example.py` that verifies:
- Sample project can resolve builtin agents
- Sample project can resolve endpoint bindings  
- Sample project can resolve private retrieval domains
- No internal-only modules are imported

### Step 4: Validate
Run the test to verify it passes.

## Risks
- Need to verify what constitutes "internal-only" modules vs public surface
- May need to adjust test based on actual Marten architecture
