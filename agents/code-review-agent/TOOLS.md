# Code Review Agent Tools

## Tool Priority

1. Review the provided diff and task context first.
2. Use skills and local context as the primary basis for findings.
3. Use GitHub or GitLab context only to enrich review context.

## Preferred Capabilities

- `github.get_issue`
- `github.create_issue_comment`

## Restrictions

- Do not let external metadata replace direct review of the provided code context.
- Do not open or modify pull requests as part of review reasoning.

## Operational Rules

- Tool output may enrich context.
- Final review findings must still follow the structured review contract.
