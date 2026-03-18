# Ralph Tools

## Tool Priority

1. Use skills for planning and implementation reasoning.
2. Use repository-local worktree and validation tools for code changes.
3. Use GitHub MCP for issue comments, labels, and PR creation.
4. If required GitHub MCP tools are unavailable, stop and surface the missing `mcp.json` configuration.

## Preferred MCP Capabilities

- `github.get_issue`
- `github.create_issue_comment`
- `github.apply_labels`
- `github.create_pull_request`

## Restrictions

- External tools are for state synchronization, not for replacing repository reasoning.
- Do not mutate unrelated issues or PRs.
- Do not open multiple competing PRs for the same task.

## Operational Rules

- Keep tool usage aligned with the current task state.
- If a tool action fails, preserve a clear error summary for retry or handoff.
