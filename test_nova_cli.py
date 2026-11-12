import io
import unittest
from types import SimpleNamespace
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import nova
from core.harness import auto_tune_environment, get_harness_profile
from core.a2a_protocol import build_agent_card, format_user_to_agent_message, format_agent_to_user_response
from core.hud import render_hud_snapshot


class NovaCliTests(unittest.TestCase):
    def test_continue_command_resumes_task_without_voice(self):
        assistant = SimpleNamespace(resume_task=Mock(return_value="resumed job-test"))
        with patch("nova.NovaVoiceAssistant", return_value=assistant), \
                patch("sys.argv", ["nova", "continue", "job-test", "--no-voice"]), \
                redirect_stdout(io.StringIO()):
            nova.main()

        assistant.resume_task.assert_called_once_with("job-test", voice_output=False)

    def test_discard_task_command_removes_paused_task(self):
        store = SimpleNamespace(delete_agent_task=Mock(return_value=True))
        with patch("nova.JobStore", return_value=store), \
                patch("sys.argv", ["nova", "discard-task", "job-test"]), \
                redirect_stdout(io.StringIO()):
            nova.main()

        store.delete_agent_task.assert_called_once_with("job-test")

    def test_auto_tune_supports_gemma_qwen_deepseek_and_gpt_oss(self):
        for name, expected in [
            ("gemma-4-31b", "gemma"),
            ("Qwen3.5-35B-A3B-4bit", "qwen"),
            ("DeepSeek-R1-Distill-Qwen-32B", "deepseek"),
            ("get-oss-20b", "gpt-oss"),
            ("mlx-community/gpt-oss-20b-4bit", "gpt-oss"),
        ]:
            prof = get_harness_profile(name)
            self.assertEqual(prof.family, expected)
            tuned = auto_tune_environment(name, persist=False)
            self.assertEqual(tuned["family"], expected)

    def test_model_catalog_preconfigures_architecture_variants(self):
        from core.model_manager import resolve_model_choice

        for choice, expected in (("qwen2.5", ("qwen", "qwen2.5")), ("qwen3.5", ("qwen", "qwen3.5")),
                                 ("gemma3", ("gemma", "gemma3")), ("gemma4", ("gemma", "gemma4")),
                                 ("gpt-oss:20b", "gpt-oss")):
            resolved = resolve_model_choice(choice)
            if isinstance(expected, tuple):
                self.assertEqual((resolved["family"], resolved["variant"]), expected)
            else:
                self.assertEqual(resolved["family"], expected)
            self.assertTrue(resolved["repo_id"])

    def test_hud_snapshot_preserves_input_buffer(self):
        frame = render_hud_snapshot(input_buffer="claw typing test", last_response="Active")
        self.assertIn("claw typing test", frame)
        self.assertIn("NOVA-CLAW", frame)

    def test_a2a_protocol_envelopes_follow_spec(self):
        card = build_agent_card([{"function": {"name": "save_note", "description": "Save note"}}])
        self.assertEqual(card["protocolVersion"], "0.2.5")
        u2a = format_user_to_agent_message("Check status", context_memories=["mem1"])
        self.assertEqual(u2a["role"], "user")
        self.assertEqual(u2a["parts"][0]["type"], "text")
        a2u = format_agent_to_user_response("job-1", "Done", job_status="COMPLETE")
        self.assertEqual(a2u["status"]["state"], "completed")


if __name__ == "__main__":
    unittest.main()
