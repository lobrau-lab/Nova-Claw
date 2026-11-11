import io
import unittest
from types import SimpleNamespace
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import nova


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


if __name__ == "__main__":
    unittest.main()
