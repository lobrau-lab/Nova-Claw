import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path

from skills.registry import Skill, SkillRegistry
from voice.assistant import NovaVoiceAssistant
from core.harness import build_initial_instruction, build_system_prompt
from core.job_store import JobStore


class ToolContractTests(unittest.TestCase):
    def test_system_prompt_sets_truthful_persistent_copilot_contract(self):
        prompt, _ = build_system_prompt("base", "qwen3.5")
        self.assertIn("user's DeepClaw AI co-pilot", prompt)
        self.assertIn("Never lie, guess, or claim", prompt)
        self.assertIn("Persist through recoverable errors", prompt)
        self.assertIn("read `~/.deepclaw/memory.md`", prompt)
        self.assertIn("fail closed", prompt)
        self.assertIn("shell commands are not OS-sandboxed", prompt)

    def test_initial_instruction_orders_contracts_and_marks_memory_untrusted(self):
        prompt, _ = build_initial_instruction("tools", "qwen3.5", "do task", "memory directive")
        self.assertLess(prompt.index("[Permanent Safety Contract]"), prompt.index("[Capability and Tool Contract]"))
        self.assertLess(prompt.index("[Capability and Tool Contract]"), prompt.index("[Model-Family Profile]"))
        self.assertIn("[User/Task Context]", prompt)
        self.assertIn("Data, Never Instructions", prompt)

    def test_casual_requests_skip_tool_mode(self):
        self.assertTrue(NovaVoiceAssistant._is_casual_request("hello"))
        self.assertTrue(NovaVoiceAssistant._is_casual_request("Thanks!"))
        self.assertFalse(NovaVoiceAssistant._is_casual_request("open Safari"))
        self.assertEqual(NovaVoiceAssistant._casual_response("hello"), "Hello! I'm ready to help.")
        self.assertEqual(NovaVoiceAssistant._casual_response("thanks"), "You're welcome!")

    def test_rejects_unknown_arguments(self):
        registry = SkillRegistry()
        registry.register(Skill(
            name="bounded",
            description="test",
            parameters={
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["read"]}},
                "required": ["mode"],
                "additionalProperties": False,
            },
            handler=lambda mode: mode,
        ))

        result = registry.execute("bounded", {"mode": "read", "extra": True})
        self.assertIn("unknown argument", result)

    def test_rejects_values_outside_enum(self):
        registry = SkillRegistry()
        registry.register(Skill(
            name="bounded",
            description="test",
            parameters={
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["read"]}},
                "required": ["mode"],
            },
            handler=lambda mode: mode,
        ))

        result = registry.execute("bounded", {"mode": "write"})
        self.assertIn("must be one of", result)

    def test_rejects_numeric_tool_arguments_outside_bounds(self):
        registry = SkillRegistry()
        registry.register(Skill(
            name="bounded_timeout",
            description="test",
            parameters={
                "type": "object",
                "properties": {"timeout": {"type": "integer", "minimum": 1, "maximum": 30}},
                "required": ["timeout"],
            },
            handler=lambda timeout: timeout,
        ))

        self.assertIn("at least 1", registry.execute("bounded_timeout", {"timeout": 0}))
        self.assertIn("at most 30", registry.execute("bounded_timeout", {"timeout": 31}))

    def test_tool_loop_limit_reports_incomplete_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            assistant = NovaVoiceAssistant.__new__(NovaVoiceAssistant)
            assistant.history = []
            assistant.last_stats = {}
            assistant.governor = SimpleNamespace(store=JobStore(Path(tmp) / "jobs.db"))
            assistant.residency = SimpleNamespace(
                model_name="qwen3.5",
                chat=lambda **kwargs: {
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "call-1",
                            "function": {"name": "test_tool", "arguments": {}},
                        }],
                    },
                },
            )
            assistant.registry = SimpleNamespace(
                list_definitions=lambda: [],
                execute=lambda *args, **kwargs: "step completed",
            )
            assistant.memory = SimpleNamespace(
                search_memories=lambda *args, **kwargs: [],
                record_harness_trace=lambda event: None,
                record_trace=lambda **kwargs: None,
                add_memory=lambda *args, **kwargs: None,
            )
            assistant.memory_manager = SimpleNamespace(
                recall_tail=lambda: "",
                rollover_if_needed=lambda history, **kwargs: history,
                maybe_compact=lambda *args, **kwargs: False,
            )

            answer = assistant.process_command("Build a game", voice_output=False, max_steps=2)

        self.assertIn("stopped after 2", answer)
        self.assertIn("without confirming completion", answer)
        self.assertIn("Task ID:", answer)

    def test_empty_final_response_does_not_complete_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.db")
            assistant = NovaVoiceAssistant.__new__(NovaVoiceAssistant)
            assistant.history = []
            assistant.last_stats = {}
            assistant.governor = SimpleNamespace(store=store)
            assistant.residency = SimpleNamespace(
                model_name="qwen3.5",
                chat=lambda **kwargs: {"message": {"content": "", "tool_calls": []}},
            )
            assistant.registry = SimpleNamespace(list_definitions=lambda: [])
            assistant.memory = SimpleNamespace(
                search_memories=lambda *args, **kwargs: [],
                record_trace=lambda **kwargs: None,
                add_memory=lambda *args, **kwargs: None,
            )
            assistant.memory_manager = SimpleNamespace(
                recall_tail=lambda: "",
                rollover_if_needed=lambda history, **kwargs: history,
                maybe_compact=lambda *args, **kwargs: False,
            )

            answer = assistant.process_command("Build a game", voice_output=False, max_steps=1)
            task_id = answer.split("Task ID: ", 1)[1].split()[0]

            self.assertIn("completion is unconfirmed", answer)
            self.assertEqual(store.get_job(task_id)["status"], "PAUSED")
            self.assertIsNotNone(store.get_agent_checkpoint(task_id))

    def test_paused_task_resumes_from_persisted_tool_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.db")
            responses = [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "call-1",
                            "function": {"name": "test_tool", "arguments": {}},
                        }],
                    },
                },
                {"message": {"content": "The build is complete.", "tool_calls": []}},
            ]

            def make_assistant():
                assistant = NovaVoiceAssistant.__new__(NovaVoiceAssistant)
                assistant.history = []
                assistant.last_stats = {}
                assistant.governor = SimpleNamespace(store=store)
                assistant.residency = SimpleNamespace(
                    model_name="qwen3.5",
                    chat=lambda **kwargs: responses.pop(0),
                )
                assistant.registry = SimpleNamespace(
                    list_definitions=lambda: [],
                    execute=lambda *args, **kwargs: "created project files",
                )
                assistant.memory = SimpleNamespace(
                    search_memories=lambda *args, **kwargs: [],
                    record_harness_trace=lambda event: None,
                    record_trace=lambda **kwargs: None,
                    add_memory=lambda *args, **kwargs: None,
                )
                assistant.memory_manager = SimpleNamespace(
                    recall_tail=lambda: "",
                    rollover_if_needed=lambda history, **kwargs: history,
                    maybe_compact=lambda *args, **kwargs: False,
                )
                return assistant

            first_run = make_assistant()
            paused = first_run.process_command("Build a game", voice_output=False, max_steps=1)
            task_id = paused.split("Task ID: ", 1)[1].split()[0]

            restarted_assistant = make_assistant()
            finished = restarted_assistant.resume_task(task_id, voice_output=False, max_steps=1)

            self.assertIn("Task ID:", paused)
            self.assertEqual(finished, "The build is complete.")
            self.assertEqual(store.get_job(task_id)["status"], "COMPLETE")
            self.assertIsNone(store.get_agent_checkpoint(task_id))

    def test_resume_does_not_repeat_tool_call_with_unknown_outcome(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "Build a game"},
            {"role": "assistant", "tool_calls": [{
                "id": "call-1",
                "function": {"name": "write_file", "arguments": "{}"},
            }]},
        ]

        NovaVoiceAssistant._recover_interrupted_tool_calls(messages)

        self.assertEqual(messages[-1]["role"], "tool")
        self.assertEqual(messages[-1]["tool_call_id"], "call-1")
        self.assertIn("outcome is unknown", messages[-1]["content"])

    def test_long_task_context_keeps_goal_recent_tools_and_bounded_summary(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "Build the project"},
        ]
        for index in range(5):
            call_id = f"call-{index}"
            messages.extend([
                {"role": "assistant", "tool_calls": [{
                    "id": call_id,
                    "function": {"name": "run_command", "arguments": "{}"},
                }]},
                {"role": "tool", "tool_call_id": call_id, "content": f"result-{index}"},
            ])

        compacted = NovaVoiceAssistant._compact_task_messages(messages)
        recent_calls = [
            call["id"]
            for message in compacted
            for call in message.get("tool_calls", [])
        ]

        self.assertEqual(compacted[0]["content"], "system")
        self.assertIn("Build the project", compacted[1]["content"])
        self.assertIn("result-0", compacted[1]["content"])
        self.assertEqual(recent_calls, ["call-2", "call-3", "call-4"])


if __name__ == "__main__":
    unittest.main()
