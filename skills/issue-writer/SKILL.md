---
name: issue-writer
description: Draft an implementation-ready GitHub issue from a user request.
---

# Purpose

Use this skill when a user request should be converted into a downstream execution unit.

## Required Output

Return strict JSON with:

- `title`: concise issue title
- `body`: markdown issue body
- `labels`: list of short labels

## Drafting Rules

1. Preserve the user's original goal.
2. State expected implementation scope and acceptance checks.
3. Include `agent:ralph` and `workflow:sleep-coding` so Ralph can discover and claim the issue.
4. Keep labels short and machine-friendly.

## Quality Bar

- The issue must be understandable without the original chat transcript.
- The body must separate user intent from implementation guidance.
- Unknown details should be recorded as assumptions or open questions, not silently invented.

## Failure / Ambiguity Rules

- If the request is ambiguous, keep the issue executable by explicitly listing ambiguity in the body.
- Do not return prose outside the JSON contract.
