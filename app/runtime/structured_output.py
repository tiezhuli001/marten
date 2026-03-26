from __future__ import annotations

import ast
import json
import re
from typing import Any


def parse_structured_object(output_text: str) -> Any:
    """Best-effort boundary extractor for model-generated objects.

    This helper is intentionally tolerant: it first tries strict JSON, then
    extracts the outermost object slice, normalizes common Ruby-style hash
    rockets, and finally falls back to ``ast.literal_eval``.

    It is not the source of truth for workflow correctness. Callers must still
    enforce workflow-specific schema validation and fail-closed behavior.
    """
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        pass

    candidate = _extract_object_slice(output_text)
    if candidate is None:
        raise json.JSONDecodeError("No structured object found", output_text, 0)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        normalized_candidate = _normalize_hash_rocket(candidate)
        if normalized_candidate != candidate:
            try:
                return json.loads(normalized_candidate)
            except json.JSONDecodeError:
                candidate = normalized_candidate
        try:
            return ast.literal_eval(candidate)
        except (SyntaxError, ValueError) as exc:
            raise json.JSONDecodeError(str(exc), output_text, 0) from exc


def _extract_object_slice(output_text: str) -> str | None:
    start = output_text.find("{")
    end = output_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return output_text[start : end + 1]


def _normalize_hash_rocket(candidate: str) -> str:
    normalized = re.sub(
        r'([{\[,]\s*):?([A-Za-z_][A-Za-z0-9_]*)\s*=>',
        r'\1"\2":',
        candidate,
    )
    normalized = normalized.replace("=>", ":")
    normalized = re.sub(r"\bnil\b", "null", normalized)
    return normalized
