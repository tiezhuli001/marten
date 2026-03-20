# Contributing

Thanks for considering a contribution to Marten.

## Development

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

Copy the required config first:

```bash
cp .env.example .env
cp mcp.json.example mcp.json
cp models.json.example models.json
cp platform.json.example platform.json
```

JSON config is the primary control surface:

- `mcp.json`: MCP servers and their auth/env
- `models.json`: provider keys, bases, models, profiles
- `platform.json`: repo, worker, review, git, validation behavior
- `agents.json`: optional agent-spec overrides

Use `.env` for runtime overrides and deployment-specific values. It is not the only place secrets can live.

## Tests

Run the full suite before opening a pull request:

```bash
python -m unittest discover -s tests -v
```

## Pull Requests

- Keep changes scoped and easy to review.
- Update documentation when behavior changes.
- Add or update tests for non-trivial changes.
- Avoid committing local secrets, worktree artifacts, or internal handoff notes.

## Design Direction

Marten is intentionally local-first:

- MCP and APIs handle platform operations.
- Local worktrees and checkouts handle code context and execution.
- Agent behavior should prefer explicit configuration over hidden fallbacks.
