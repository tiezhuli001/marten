# Contributing

Thanks for considering a contribution to Marten.

## Development

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

Copy the example configuration files before running the service:

```bash
cp .env.example .env
cp agents.json.example agents.json
cp models.json.example models.json
cp platform.json.example platform.json
cp mcp.json.example mcp.json
```

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
