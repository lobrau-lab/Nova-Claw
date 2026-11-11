import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.model_manager import download_model_weights
from voice.stt import LocalSpeechRecognizer
from voice.tts import LocalSpeechSynthesizer


class VoiceAndModelTests(unittest.TestCase):
    def test_stt_flags_are_converted_for_in_process_backends(self):
        recognizer = LocalSpeechRecognizer.__new__(LocalSpeechRecognizer)
        recognizer.additional_flags = ["--language", "en", "--temperature=0.2", "--word-timestamps"]
        self.assertEqual(recognizer._in_process_options(), {
            "language": "en", "temperature": 0.2, "word_timestamps": True,
        })

    def test_tts_flags_are_converted_for_in_process_backend(self):
        synthesizer = LocalSpeechSynthesizer.__new__(LocalSpeechSynthesizer)
        synthesizer.additional_flags = ["--temperature", "0.7", "--nfe-step=8"]
        self.assertEqual(synthesizer._in_process_options(), {"temperature": 0.7, "nfe_step": 8})

    def test_model_download_requires_immutable_revision(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOVA_MODEL_REVISION", None)
            result = download_model_weights("qwen", target_dir=Path(directory))
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("immutable revision", result["error"])


if __name__ == "__main__":
    unittest.main()
