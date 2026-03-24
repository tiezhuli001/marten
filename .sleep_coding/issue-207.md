# Ralph Task

- task_id: 7428b1a2-3a47-4731-9653-7c0d026a3371
- issue_number: 207
- branch: codex/issue-207-sleep-coding

# Task 10: Add a standalone sample private project

## Context
Create a sample private project that demonstrates how users can configure:
- Custom agents
- Endpoint bindings
- Private retrieval domains

Using only public surface APIs without importing internal-only modules.

## Validation Strategy
1. Write a test that verifies the sample project can be loaded and validated
2. Confirm it fails initially (RED)
3. Create the minimal sample project
4. Verify the test passes (GREEN)

## Files Created
- `examples/private_agent_suite/` - Complete sample project structure
- `tests/test_private_project_example.py` - Validation test

## Risks
- The test assumes certain public APIs exist; may need adjustment if API surface differs
- MCP configuration example is placeholder; real usage would need actual server configs

## Test Approach
The test verifies:
1. Sample project directory structure exists
2. JSON configuration files are valid
3. No internal modules are imported in the sample configs
4. Required fields are present in agents.json and platform.json
