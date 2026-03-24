"""Test that the private project example can be loaded using only public surface APIs."""

import unittest
import os
import json


class TestPrivateProjectExample(unittest.TestCase):
    """Validate that the private_agent_suite example uses only public surface."""

    def setUp(self):
        """Set up test fixtures."""
        self.example_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'examples',
            'private_agent_suite'
        )

    def test_agents_json_exists_and_valid(self):
        """Verify agents.json exists and is valid JSON."""
        agents_path = os.path.join(self.example_path, 'agents.json')
        self.assertTrue(os.path.exists(agents_path), 
            "agents.json should exist in private_agent_suite")
        
        with open(agents_path, 'r') as f:
            agents_config = json.load(f)
        
        self.assertIn('agents', agents_config)
        self.assertIn('version', agents_config)
        
        # Verify builtin agents are properly defined
        for agent in agents_config.get('agents', []):
            self.assertIn('id', agent)
            self.assertIn('name', agent)
            self.assertTrue(agent.get('builtin', False), 
                "Agents should be marked as builtin")

    def test_platform_json_exists_and_valid(self):
        """Verify platform.json exists and is valid JSON."""
        platform_path = os.path.join(self.example_path, 'platform.json')
        self.assertTrue(os.path.exists(platform_path), 
            "platform.json should exist in private_agent_suite")
        
        with open(platform_path, 'r') as f:
            platform_config = json.load(f)
        
        self.assertIn('platform', platform_config)
        self.assertIn('version', platform_config)

    def test_models_json_example_exists(self):
        """Verify models.json.example template exists."""
        models_path = os.path.join(self.example_path, 'models.json.example')
        self.assertTrue(os.path.exists(models_path), 
            "models.json.example should exist")
        
        with open(models_path, 'r') as f:
            models_config = json.load(f)
        
        self.assertIn('models', models_config)

    def test_mcp_json_example_exists(self):
        """Verify mcp.json.example template exists."""
        mcp_path = os.path.join(self.example_path, 'mcp.json.example')
        self.assertTrue(os.path.exists(mcp_path), 
            "mcp.json.example should exist")

    def test_private_docs_directory_exists(self):
        """Verify private_docs directory exists."""
        docs_path = os.path.join(self.example_path, 'private_docs')
        self.assertTrue(os.path.exists(docs_path), 
            "private_docs directory should exist")
        self.assertTrue(os.path.isdir(docs_path))

    def test_skills_directory_exists(self):
        """Verify skills directory exists."""
        skills_path = os.path.join(self.example_path, 'skills')
        self.assertTrue(os.path.exists(skills_path), 
            "skills directory should exist")
        self.assertTrue(os.path.isdir(skills_path))

    def test_endpoint_bindings_configured(self):
        """Verify endpoint bindings are configured in agents.json."""
        agents_path = os.path.join(self.example_path, 'agents.json')
        
        with open(agents_path, 'r') as f:
            agents_config = json.load(f)
        
        self.assertIn('endpoint_bindings', agents_config)
        bindings = agents_config['endpoint_bindings']
        self.assertGreater(len(bindings), 0, 
            "Should have at least one endpoint binding configured")

    def test_private_domains_configured(self):
        """Verify private retrieval domains are configured in agents.json."""
        agents_path = os.path.join(self.example_path, 'agents.json')
        
        with open(agents_path, 'r') as f:
            agents_config = json.load(f)
        
        self.assertIn('private_domains', agents_config)
        domains = agents_config['private_domains']
        self.assertGreater(len(domains), 0, 
            "Should have at least one private domain configured")


if __name__ == '__main__':
    unittest.main()
