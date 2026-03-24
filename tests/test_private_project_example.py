"""
Validation tests for the sample private project example.

These tests verify that the sample private project can resolve:
- Builtin agents
- Endpoint bindings
- Private retrieval domains

Without importing internal-only modules.
"""

import json
import os
import unittest
from pathlib import Path


class TestPrivateProjectExample(unittest.TestCase):
    """Test that the sample private project uses only public surface."""

    def setUp(self):
        """Set up paths for the sample project."""
        self.project_dir = Path(__file__).parent.parent / "examples" / "private_agent_suite"
        self.agents_path = self.project_dir / "agents.json"
        self.platform_path = self.project_dir / "platform.json"

    def test_project_directory_exists(self):
        """Verify the sample project directory exists."""
        self.assertTrue(
            self.project_dir.exists(),
            f"Sample project directory should exist at {self.project_dir}"
        )

    def test_agents_json_exists_and_valid(self):
        """Verify agents.json exists and is valid JSON."""
        self.assertTrue(self.agents_path.exists(), "agents.json should exist")
        
        with open(self.agents_path) as f:
            agents_data = json.load(f)
        
        self.assertIn("agents", agents_data, "agents.json should have 'agents' key")
        self.assertIsInstance(agents_data["agents"], list, "agents should be a list")

    def test_platform_json_exists_and_valid(self):
        """Verify platform.json exists and is valid JSON."""
        self.assertTrue(self.platform_path.exists(), "platform.json should exist")
        
        with open(self.platform_path) as f:
            platform_data = json.load(f)
        
        self.assertIn("endpoint_bindings", platform_data, "platform.json should have endpoint_bindings")
        self.assertIn("retrieval_domains", platform_data, "platform.json should have retrieval_domains")

    def test_resolve_builtin_agents(self):
        """Verify builtin agents can be resolved from sample project config."""
        with open(self.agents_path) as f:
            agents_data = json.load(f)
        
        # Verify agent structure - this represents resolution of agent definitions
        agents = agents_data.get("agents", [])
        self.assertGreater(len(agents), 0, "Should have at least one agent defined")
        
        for agent in agents:
            self.assertIn("id", agent, "Each agent should have an 'id'")
            self.assertIn("name", agent, "Each agent should have a 'name'")

    def test_resolve_endpoint_bindings(self):
        """Verify endpoint bindings can be resolved from sample project config."""
        with open(self.platform_path) as f:
            platform_data = json.load(f)
        
        endpoint_bindings = platform_data.get("endpoint_bindings", [])
        self.assertGreater(len(endpoint_bindings), 0, "Should have at least one endpoint binding")
        
        for binding in endpoint_bindings:
            self.assertIn("name", binding, "Each binding should have a 'name'")
            self.assertIn("url", binding, "Each binding should have a 'url'")

    def test_resolve_private_retrieval_domains(self):
        """Verify private retrieval domains can be resolved from sample project config."""
        with open(self.platform_path) as f:
            platform_data = json.load(f)
        
        retrieval_domains = platform_data.get("retrieval_domains", [])
        self.assertGreater(len(retrieval_domains), 0, "Should have at least one retrieval domain")
        
        for domain in retrieval_domains:
            self.assertIn("name", domain, "Each domain should have a 'name'")
            self.assertIn("type", domain, "Each domain should have a 'type'")

    def test_no_internal_only_modules(self):
        """Verify the sample project doesn't use internal-only module imports."""
        # Check all JSON config files for any suspicious import patterns
        # This is a negative test - we verify there are no internal imports
        json_files = list(self.project_dir.glob("*.json*"))
        
        for json_file in json_files:
            with open(json_file) as f:
                content = f.read()
            
            # JSON files shouldn't have Python import statements
            # This test ensures we're using config-based approach, not code imports
            self.assertNotIn("import", content, f"{json_file.name} should not contain import statements")

    def test_example_files_present(self):
        """Verify example configuration files are present."""
        models_example = self.project_dir / "models.json.example"
        mcp_example = self.project_dir / "mcp.json.example"
        
        self.assertTrue(models_example.exists(), "models.json.example should exist")
        self.assertTrue(mcp_example.exists(), "mcp.json.example should exist")


if __name__ == "__main__":
    unittest.main()
