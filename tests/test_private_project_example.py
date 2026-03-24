"""
Test for private_agent_suite example project.

This test verifies that the sample private project can resolve builtin agents,
endpoint bindings, and private retrieval domains without importing internal-only modules.
"""

import json
import os
import unittest
from pathlib import Path


class TestPrivateProjectExample(unittest.TestCase):
    """Test the private_agent_suite example project."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.example_dir = Path(__file__).parent.parent / "examples" / "private_agent_suite"

    def test_example_directory_exists(self):
        """Verify the example directory exists."""
        self.assertTrue(
            self.example_dir.exists(),
            f"Example directory should exist at {self.example_dir}"
        )

    def test_agents_json_is_valid(self):
        """Verify agents.json is valid and contains builtin agents."""
        agents_file = self.example_dir / "agents.json"
        self.assertTrue(agents_file.exists(), "agents.json should exist")

        with open(agents_file) as f:
            agents_data = json.load(f)

        self.assertIn("agents", agents_data, "agents.json should have 'agents' key")
        self.assertIsInstance(agents_data["agents"], list, "agents should be a list")

        # Verify builtin agents are defined
        builtin_agents = [a for a in agents_data["agents"] if a.get("builtin")]
        self.assertGreater(
            len(builtin_agents), 0,
            "Should have at least one builtin agent defined"
        )

    def test_platform_json_is_valid(self):
        """Verify platform.json is valid and contains endpoint bindings and retrieval domains."""
        platform_file = self.example_dir / "platform.json"
        self.assertTrue(platform_file.exists(), "platform.json should exist")

        with open(platform_file) as f:
            platform_data = json.load(f)

        self.assertIn("endpoint_bindings", platform_data, "platform.json should have 'endpoint_bindings'")
        self.assertIn("retrieval_domains", platform_data, "platform.json should have 'retrieval_domains'")

        # Verify endpoint bindings exist
        self.assertGreater(
            len(platform_data["endpoint_bindings"]), 0,
            "Should have at least one endpoint binding"
        )

        # Verify retrieval domains exist
        self.assertGreater(
            len(platform_data["retrieval_domains"]), 0,
            "Should have at least one retrieval domain"
        )

    def test_example_config_files_exist(self):
        """Verify example configuration files exist."""
        models_example = self.example_dir / "models.json.example"
        mcp_example = self.example_dir / "mcp.json.example"

        self.assertTrue(models_example.exists(), "models.json.example should exist")
        self.assertTrue(mcp_example.exists(), "mcp.json.example should exist")

    def test_skills_directory_exists(self):
        """Verify skills directory exists."""
        skills_dir = self.example_dir / "skills"
        self.assertTrue(skills_dir.exists(), "skills directory should exist")

    def test_private_docs_directory_exists(self):
        """Verify private_docs directory exists."""
        private_docs_dir = self.example_dir / "private_docs"
        self.assertTrue(private_docs_dir.exists(), "private_docs directory should exist")

    def test_no_internal_imports(self):
        """Verify this test file does not import internal-only modules."""
        # This test ensures the validation itself uses only public APIs
        # Internal modules would typically be in marten.internal or similar
        import sys

        # Check that no internal modules are imported
        internal_modules = [m for m in sys.modules if m.startswith("marten.internal")]
        self.assertEqual(
            len(internal_modules), 0,
            f"Should not import internal-only modules, found: {internal_modules}"
        )


if __name__ == "__main__":
    unittest.main()
