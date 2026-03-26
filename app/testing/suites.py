from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TestSuite:
    name: str
    description: str
    modules: tuple[str, ...]


_TEST_SUITES: dict[str, TestSuite] = {
    "quick": TestSuite(
        name="quick",
        description="Fast local regression suite without MVP end-to-end or live-chain coverage.",
        modules=(
            "tests.test_agent_runtime_policy",
            "tests.test_rag_capability",
            "tests.test_main_agent",
            "tests.test_gateway",
            "tests.test_sleep_coding",
            "tests.test_review",
            "tests.test_runtime_components",
            "tests.test_test_suites",
        ),
    ),
    "regression": TestSuite(
        name="regression",
        description="Full non-live regression suite for the current self-host main chain and its required boundary services.",
        modules=(
            "tests.test_agent_runtime_policy",
            "tests.test_channel",
            "tests.test_channel_routing",
            "tests.test_control_context",
            "tests.test_feishu",
            "tests.test_llm_runtime",
            "tests.test_rag_capability",
            "tests.test_main_agent",
            "tests.test_gateway",
            "tests.test_session_registry",
            "tests.test_sleep_coding",
            "tests.test_sleep_coding_worker",
            "tests.test_review",
            "tests.test_task_registry",
            "tests.test_automation",
            "tests.test_token_ledger",
            "tests.test_runtime_components",
            "tests.test_mvp_e2e",
            "tests.test_test_suites",
        ),
    ),
    "manual": TestSuite(
        name="manual",
        description="Non-default tests kept for future evolution surfaces or optional indexing workflows.",
        modules=(
            "tests.test_framework_public_surface",
            "tests.test_rag_indexing",
        ),
    ),
    "live": TestSuite(
        name="live",
        description="Real live-chain validation against configured MCP, LLM, and Feishu endpoints.",
        modules=("tests.test_live_chain",),
    ),
}


def get_test_suite(name: str) -> TestSuite:
    normalized = name.strip().lower() if isinstance(name, str) else ""
    if not normalized:
        normalized = "quick"
    aliases = {
        "fast": "quick",
        "default": "quick",
        "full": "regression",
        "extended": "manual",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return _TEST_SUITES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown test suite: {name}") from exc


def build_unittest_command(name: str = "quick") -> tuple[str, ...]:
    suite = get_test_suite(name)
    return ("python", "-m", "unittest", *suite.modules, "-v")
