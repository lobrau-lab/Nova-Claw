import os
import unittest
from unittest.mock import patch

from core.command_policy import inspect_command


class CommandPolicyTests(unittest.TestCase):
    def test_blocks_destructive_commands_without_approval(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOVA_ALLOW_DESTRUCTIVE_COMMANDS", None)
            decision = inspect_command("rm -rf build")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.category, "COMMAND_APPROVAL_REQUIRED")

    def test_blocks_external_commands_without_approval(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOVA_ALLOW_EXTERNAL_COMMANDS", None)
            decision = inspect_command("git push origin main")
        self.assertFalse(decision.allowed)

    def test_allows_normal_workspace_commands(self):
        self.assertTrue(inspect_command("python3 -m unittest").allowed)

    def test_explicit_approval_allows_each_category(self):
        with patch.dict(os.environ, {
            "NOVA_ALLOW_DESTRUCTIVE_COMMANDS": "1",
            "NOVA_ALLOW_EXTERNAL_COMMANDS": "1",
        }):
            self.assertTrue(inspect_command("rm -rf build").allowed)
            self.assertTrue(inspect_command("git push origin main").allowed)


if __name__ == "__main__":
    unittest.main()
