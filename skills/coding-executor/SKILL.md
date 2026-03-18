---
name: coding-executor
description: Turn an approved plan into a structured coding draft with file-level outputs.
---

# Purpose

Translate an approved plan into structured repository changes that Ralph and the platform can apply and validate.

## Execution Rules

- Produce repository-relative file paths only.
- Prefer changing existing source and test files over creating placeholders.
- Keep commit messages short and specific.
- Preserve a coherent explanation of what changed and why.

## Expected Output Qualities

- `file_changes` should be minimal and relevant
- tests should be included when behavior changes
- artifact markdown should explain intent, scope, and remaining uncertainty

## Failure / Ambiguity Rules

- If context is insufficient, keep `file_changes` empty and explain the gap in the artifact markdown.
- Do not fabricate repository files that were never referenced by the context.
- When forced to choose, prefer a no-op with a clear explanation over a misleading patch.
