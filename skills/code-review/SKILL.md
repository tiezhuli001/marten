---
name: code-review
description: Produce structured code review findings, blocking status, and repair guidance.
metadata:
  {
    "openclaw": {
      "requires": { "env": [] }
    }
  }
---

# Purpose

Return findings that automation can route directly into approve or repair actions.

## Review Rules

- Start from changed behavior, correctness, regressions, and missing tests.
- Keep findings specific and repairable.
- Use `P0` only for critical correctness or safety failures.
- Use `P1` for serious blocking defects.
- Use `P2` for meaningful but non-blocking issues.
- Use `P3` for minor concerns or cleanup.
- If no material issue exists, return an empty findings list and explain residual risks briefly.

## Output Quality

- Findings must be concise but actionable.
- Repair strategy should be implementable by a coding agent.
- Blocking status must align with the actual severities returned.

## Failure / Ambiguity Rules

- If review context is incomplete, say so explicitly in the summary or finding detail.
- Do not inflate uncertainty into `P0/P1` without concrete evidence.
