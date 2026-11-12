import unittest

from core.approval import ApprovalGate


class ApprovalGateTests(unittest.TestCase):
    def test_noninteractive_actions_fail_closed(self):
        gate = ApprovalGate(interactive=False, input_fn=lambda _: "y")
        self.assertFalse(gate.approve("type_text", "secret"))

    def test_interactive_yes_approves(self):
        gate = ApprovalGate(interactive=True, input_fn=lambda _: "yes")
        self.assertTrue(gate.approve("open_app", "Safari"))

    def test_interactive_no_denies(self):
        gate = ApprovalGate(interactive=True, input_fn=lambda _: "no")
        self.assertFalse(gate.approve("quit_app", "Safari"))
