#!/usr/bin/env python3
"""
Nova-Claw - Open-Source Whisper Speech Recognition (STT)
Supports mlx-whisper, openai-whisper, faster-whisper, and whisper.cpp CLI
with configurable models and --additional-flags pass-through.
"""

import os
import sys
import shutil
import subprocess
import tempfile
import shlex
from pathlib import Path
from typing import Optional, List
import config


class LocalSpeechRecognizer:
    def __init__(
        self,
        model_name: Optional[str] = None,
        backend: Optional[str] = None,
        additional_flags: Optional[List[str]] = None,
    ):
        self.model_name = model_name or config.WHISPER_MODEL
        self.requested_backend = (backend or config.WHISPER_BACKEND or "auto").lower()
        self.additional_flags = config.parse_additional_flags(additional_flags or config.ADDITIONAL_FLAGS)
        self._model = None
        self._backend = self._detect_backend()

    def _in_process_options(self) -> dict:
        allowed = {
            "language", "task", "temperature", "initial_prompt",
            "condition_on_previous_text", "beam_size", "best_of",
            "vad_filter", "word_timestamps",
        }
        tokens = shlex.split(" ".join(self.additional_flags))
        options = {}
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if not token.startswith("--"):
                index += 1
                continue
            key, sep, value = token[2:].partition("=")
            key = key.replace("-", "_")
            if key not in allowed:
                index += 1
                continue
            if not sep and index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                index += 1
                value = tokens[index]
            if not value:
                value = True
            elif value.lower() in {"true", "false"}:
                value = value.lower() == "true"
            else:
                try:
                    value = float(value) if "." in value else int(value)
                except ValueError:
                    pass
            options[key] = value
            index += 1
        return options

    def _detect_backend(self) -> str:
        if self.requested_backend != "auto":
            return self.requested_backend
        try:
            import mlx_whisper
            return "mlx_whisper"
        except ImportError:
            pass
        try:
            import whisper
            return "openai_whisper"
        except ImportError:
            pass
        try:
            import faster_whisper
            return "faster_whisper"
        except ImportError:
            pass
        if shutil.which("whisper-cli") or shutil.which("whisper"):
            return "whisper_cpp"
        return "fallback_simulated"

    def transcribe_audio_file(self, audio_path: Path) -> str:
        """Transcribes a .wav or .m4a audio file to text using open-source Whisper."""
        if not audio_path.exists():
            return ""

        repo_or_name = (
            self.model_name
            if "/" in self.model_name
            else f"mlx-community/whisper-{self.model_name}"
        )

        if self._backend == "mlx_whisper":
            try:
                import mlx_whisper
                res = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=repo_or_name, **self._in_process_options())
                return res.get("text", "").strip()
            except Exception as exc:
                return f"[mlx_whisper error: {exc}]"

        if self._backend == "openai_whisper":
            try:
                import whisper
                if self._model is None:
                    self._model = whisper.load_model(self.model_name)
                res = self._model.transcribe(str(audio_path), **self._in_process_options())
                return res.get("text", "").strip()
            except Exception as exc:
                return f"[openai_whisper error: {exc}]"

        if self._backend == "faster_whisper":
            try:
                from faster_whisper import WhisperModel
                if self._model is None:
                    self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                segments, _ = self._model.transcribe(str(audio_path), **self._in_process_options())
                return " ".join(seg.text.strip() for seg in segments).strip()
            except Exception as exc:
                return f"[faster_whisper error: {exc}]"

        if self._backend == "whisper_cpp":
            bin_path = shutil.which("whisper-cli") or shutil.which("whisper")
            if bin_path:
                cmd = [bin_path, "-f", str(audio_path), *self.additional_flags]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if proc.returncode == 0 and proc.stdout.strip():
                        return proc.stdout.strip()
                except Exception:
                    pass

        return f"[Speech recognition ready ({self._backend}, model={self.model_name}): install mlx-whisper or openai-whisper on macOS]"

    def record_microphone(self, duration_seconds: int = 5) -> Optional[Path]:
        """Records short audio snippet from system microphone."""
        temp_audio = Path(tempfile.gettempdir()) / f"nova_voice_{int(os.getpid())}.wav"
        if sys.platform == "darwin":
            try:
                input_dev = config.SPEECH_INPUT_DEVICE or ":0"
                cmd = [
                    "ffmpeg", "-y", "-f", "avfoundation",
                    "-i", str(input_dev),
                    "-t", str(duration_seconds),
                    *self.additional_flags,
                    str(temp_audio),
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=duration_seconds + 3)
                if temp_audio.exists() and temp_audio.stat().st_size > 1000:
                    return temp_audio
            except Exception:
                pass
        return None
