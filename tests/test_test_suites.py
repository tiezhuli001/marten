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

    def test_live_suite_contains_only_live_chain(self) -> None:
        suite = get_test_suite("live")

        self.assertEqual(suite.modules, ("tests.test_live_chain",))

    def test_build_unittest_command_defaults_to_quick_suite(self) -> None:
        command = build_unittest_command()

        self.assertEqual(command[:3], ("python", "-m", "unittest"))
        self.assertIn("tests.test_main_agent", command)
        self.assertNotIn("tests.test_live_chain", command)


if __name__ == "__main__":
    unittest.main()
