# Main Agent Tools

## Tool Priority

1. Use the `issue-writer` skill for drafting.
2. Use GitHub MCP for issue creation.
3. If required GitHub MCP tools are unavailable, stop and surface the missing `mcp.json` configuration.

## Allowed External Operations

- create GitHub issue
- read minimal repository issue context if needed

## Restrictions

- Do not use tools to guess repository state that is not required for issue drafting.
- Do not open pull requests.
- Do not mutate unrelated project state.

## Operational Rules

- Treat MCP as the mandatory execution path for GitHub operations.
- Keep issue creation deterministic once a draft is produced.
- Return machine-friendly labels that downstream workers can route on.
