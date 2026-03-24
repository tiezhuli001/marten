"""
Validation test for the private project example.

This test verifies that the sample private project can be loaded
and validated without importing internal-only modules.
"""

import json
import os
import unittest
from pathlib import Path


class TestPrivateProjectExample(unittest.TestCase):
    """Test that the private project example is valid and uses public surface only."""

    def setUp(self):
        """Set up paths for the private agent suite example."""
        self.project_dir = Path(__file__).parent.parent / "examples" / "private_agent_suite"
        self.agents_file = self.project_dir / "agents.json"
        self.platform_file = self.project_dir / "platform.json"

    def test_project_directory_exists(self):
        """Verify the private agent suite directory exists."""
        self.assertTrue(
            self.project_dir.exists(),
            f"Private project directory should exist at {self.project_dir}"
        )
        self.assertTrue(
            self.project_dir.is_dir(),
            "Private project should be a directory"
        )

    def test_agents_json_valid(self):
        """Verify agents.json is valid JSON with required structure."""
        self.assertTrue(
            self.agents_file.exists(),
            f"agents.json should exist at {self.agents_file}"
        )

        with open(self.agents_file) as f:
            agents_data = json.load(f)

        self.assertIn("agents", agents_data, "agents.json should have 'agents' key")
        self.assertIsInstance(agents_data["agents"], list, "agents should be a list")
        self.assertGreater(
            len(agents_data["agents"]), 0, "agents should have at least one agent"
        )

        # Verify agent structure
        agent = agents_data["agents"][0]
        self.assertIn("name", agent, "Agent should have a name")
        self.assertIn("description", agent, "Agent should have a description")
        self.assertIn("instructions", agent, "Agent should have instructions")

    def test_platform_json_valid(self):
        """Verify platform.json is valid JSON with required structure."""
        self.assertTrue(
            self.platform_file.exists(),
            f"platform.json should exist at {self.platform_file}"
        )

        with open(self.platform_file) as f:
            platform_data = json.load(f)

        self.assertIn("version", platform_data, "platform.json should have 'version'")
        self.assertIn("endpoints", platform_data, "platform.json should have 'endpoints'")
        self.assertIn("retrieval", platform_data, "platform.json should have 'retrieval'")

        # Verify retrieval configuration
        retrieval = platform_data["retrieval"]
        self.assertIn("domains", retrieval, "retrieval should have 'domains'")
        self.assertIn("private_docs", retrieval["domains"], 
            "retrieval should include 'private_docs' domain")

    def test_example_configs_present(self):
        """Verify example configuration files are present."""
        models_example = self.project_dir / "models.json.example"
        mcp_example = self.project_dir / "mcp.json.example"

        self.assertTrue(models_example.exists(), "models.json.example should exist")
        self.assertTrue(mcp_example.exists(), "mcp.json.example should exist")

    def test_no_internal_imports_in_configs(self):
        """Verify config files don't import internal modules."""
        # This test verifies the configs are pure JSON without Python imports
        # Internal module references would be in code, not JSON configs
        config_files = ["agents.json", "platform.json"]

        for config_file in config_files:
            with open(self.project_dir / config_file) as f:
                content = f.read()

            # JSON files should not contain Python import statements
            self.assertNotIn("import", content, 
                f"{config_file} should not contain Python imports")
            self.assertNotIn("from ", content,
                f"{config_file} should not contain Python 'from' statements")


if __name__ == "__main__":
    unittest.main()
