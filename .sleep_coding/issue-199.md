# Ralph Task

- task_id: ae45f874-c208-4d78-8e9a-288c78271e1f
- issue_number: 199
- branch: codex/issue-199-sleep-coding

# Task 10: Add a standalone sample private project

## Context
The Marten framework needs a sample private project that demonstrates how users can configure private agent suites using only public surface APIs, builtin agents, endpoint bindings, and private retrieval domains.

## Status
This is a new feature implementation following the sleep-coding workflow: RED → GREEN.

## Implementation Plan

1. **Explore existing codebase** - Understand what public APIs are available and how to configure builtin agents, endpoint bindings, and private retrieval domains
2. **Create test-first validation** - Write a test that verifies the sample project can load without importing internal modules
3. **Create minimal sample project** - Use only public surface and supported extension config
4. **Verify GREEN** - Run tests to confirm the implementation works

## Files to Create
- `examples/private_agent_suite/README.md` - Documentation for the sample
- `examples/private_agent_suite/agents.json` - Agent configuration
- `examples/private_agent_suite/platform.json` - Platform configuration
- `examples/private_agent_suite/models.json.example` - Model configuration template
- `examples/private_agent_suite/mcp.json.example` - MCP configuration template
- `examples/private_agent_suite/skills/README.md` - Skills documentation
- `examples/private_agent_suite/private_docs/README.md` - Private docs placeholder
- `tests/test_private_project_example.py` - Validation test

## Risks
- Need to verify what public APIs exist for agent configuration
- Need to ensure we don't use internal-only modules in the sample
- The test validation needs to check that no internal imports occur

## Validation Commands
```bash
python -m unittest tests.test_private_project_example -v
```

## Output
Implementation will produce strict JSON with artifact_markdown, commit_message, and file_changes keys.
