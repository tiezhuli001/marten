---
name: coding-planner
description: Produce a small, execution-ready implementation plan for a coding task.
---

# Purpose

Turn issue context into a plan that Ralph can execute without widening scope unnecessarily.

## Planning Rules

- Extract the smallest viable code change that satisfies the issue.
- Name the most likely files or modules that need updates.
- Include concrete validation commands, with tests first.
- Call out ambiguity or missing context explicitly in risks.

## Expected Shape

The plan should make clear:

- intended code areas
- expected behavior change
- validation path
- explicit risks or unknowns

## Failure / Ambiguity Rules

- If the repository context is too weak, reduce certainty instead of inventing specifics.
- Prefer a narrower plan over a broad speculative plan.
