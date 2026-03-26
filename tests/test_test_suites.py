import unittest

from app.testing.suites import build_unittest_command, get_test_suite


class TestSuiteDefinitionsTests(unittest.TestCase):
    def test_quick_suite_excludes_live_and_e2e_modules(self) -> None:
        suite = get_test_suite("quick")

        self.assertEqual(suite.name, "quick")
        self.assertNotIn("tests.test_live_chain", suite.modules)
        self.assertNotIn("tests.test_mvp_e2e", suite.modules)
        self.assertIn("tests.test_main_agent", suite.modules)

    def test_regression_suite_keeps_live_separate(self) -> None:
        suite = get_test_suite("regression")

        self.assertEqual(suite.name, "regression")
        self.assertIn("tests.test_mvp_e2e", suite.modules)
        self.assertNotIn("tests.test_live_chain", suite.modules)
        self.assertIn("tests.test_feishu", suite.modules)
        self.assertIn("tests.test_token_ledger", suite.modules)
        self.assertIn("tests.test_llm_runtime", suite.modules)
        self.assertNotIn("tests.test_framework_public_surface", suite.modules)

    def test_manual_suite_contains_optional_indexing_tests(self) -> None:
        suite = get_test_suite("manual")

        self.assertEqual(
            suite.modules,
            (
                "tests.test_framework_public_surface",
                "tests.test_rag_indexing",
            ),
        )

    def test_live_suite_contains_only_live_chain(self) -> None:
        suite = get_test_suite("live")

        self.assertEqual(suite.modules, ("tests.test_live_chain",))

    def test_build_unittest_command_defaults_to_quick_suite(self) -> None:
        command = build_unittest_command()

        self.assertEqual(command[:3], ("python", "-m", "unittest"))
        self.assertIn("tests.test_main_agent", command)
        self.assertNotIn("tests.test_live_chain", command)

    def test_extended_alias_maps_to_manual_suite(self) -> None:
        suite = get_test_suite("extended")

        self.assertEqual(suite.name, "manual")


if __name__ == "__main__":
    unittest.main()
