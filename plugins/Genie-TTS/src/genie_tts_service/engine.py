"""Serialized adapter around Genie's process-global inference state."""

from __future__ import annotations

import ctypes
import os
import tempfile
import threading
from pathlib import Path
from types import ModuleType

from .audio import normalize_wav
from .config import ServiceConfig, VoiceConfig


class EngineError(RuntimeError):
    """Genie failed to initialize or synthesize a complete audio file."""


class GenieEngine:
    def __init__(self, config: ServiceConfig):
        self.config = config
        self._lock = threading.Lock()
        self._genie: ModuleType | None = None
        self._loaded: set[str] = set()
        self._last_error = ""

    def health(self) -> tuple[bool, list[str]]:
        problems = self.config.problems()
        if problems:
            return False, problems
        try:
            with self._lock:
                self._ensure_loaded(self.config.voice(self.config.default_voice_id))
        except Exception as exc:
            self._last_error = str(exc)
            return False, [self._last_error]
        return True, []

    def memory_status(self) -> dict:
        available = _available_memory_bytes()
        return {
            "available_gib": (
                None if available is None else round(available / 1024 ** 3, 2)
            ),
        }

    def voices(self) -> list[dict]:
        return [voice.public() for voice in self.config.voices]

    def update_config(self, config: ServiceConfig) -> None:
        with self._lock:
            self.config = config

    def synthesize(self, voice: VoiceConfig, text: str) -> tuple[bytes, int]:
        with self._lock:
            self._ensure_loaded(voice)
            assert self._genie is not None
            fd, output_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                os.unlink(output_path)
                self._genie.set_reference_audio(
                    character_name=voice.id,
                    audio_path=str(voice.reference_audio),
                    audio_text=voice.reference_text,
                    language=voice.reference_language,
                )
                self._genie.tts(
                    character_name=voice.id,
                    text=text,
                    play=False,
                    split_sentence=False,
                    save_path=output_path,
                )
                path = Path(output_path)
                if not path.is_file() or path.stat().st_size <= 44:
                    raise EngineError("Genie 未生成完整音频文件")
                return normalize_wav(path.read_bytes())
            except EngineError:
                raise
            except Exception as exc:
                raise EngineError(_friendly_error("Genie 合成失败", exc)) from exc
            finally:
                try:
                    Path(output_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def _ensure_loaded(self, voice: VoiceConfig | None) -> None:
        if voice is None:
            raise EngineError("默认音色未配置")
        if self._genie is None:
            # Genie resolves all runtime data during import, so this must happen first.
            os.environ["GENIE_DATA_DIR"] = str(self.config.genie_data_dir)
            try:
                import genie_tts as genie
            except Exception as exc:
                raise EngineError(_friendly_error("无法加载 genie-tts 运行时", exc)) from exc
            self._genie = genie
        if voice.id not in self._loaded:
            try:
                self._genie.load_character(
                    character_name=voice.id,
                    onnx_model_dir=str(voice.model_dir),
                    language=voice.language,
                )
            except Exception as exc:
                raise EngineError(_friendly_error(f"无法加载音色 {voice.id}", exc)) from exc
            self._loaded.add(voice.id)


def _friendly_error(context: str, exc: Exception) -> str:
    detail = str(exc).strip()
    normalized = detail.lower()
    memory_markers = (
        "out of memory", "not enough memory", "bad_alloc",
        "failed to allocate", "memory allocation", "cannot allocate memory",
        "内存不足", "内存分配失败",
    )
    if isinstance(exc, MemoryError) or any(marker in normalized for marker in memory_markers):
        return f"{context}：运行时内存不足，请关闭占用内存较高的程序后重试"
    return f"{context}: {detail or type(exc).__name__}"


def _available_memory_bytes() -> int | None:
    if os.name != "nt":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    except (AttributeError, OSError):
        pass
    return None
