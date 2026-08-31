"""Configuration boundary for the Genie service."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path


class ConfigurationError(ValueError):
    """The plugin configuration is missing or invalid."""


@dataclass(frozen=True)
class VoiceConfig:
    id: str
    name: str
    model_dir: Path
    language: str
    reference_audio: Path
    reference_text: str
    reference_language: str
    gender: str | None = None
    description: str = ""

    def problems(self) -> list[str]:
        problems: list[str] = []
        if not self.model_dir.is_dir():
            problems.append(f"音色 {self.id} 的模型目录不存在: {self.model_dir}")
        if not self.reference_audio.is_file():
            problems.append(f"音色 {self.id} 的参考音频不存在: {self.reference_audio}")
        if not self.reference_text.strip():
            problems.append(f"音色 {self.id} 缺少参考音频文本")
        return problems

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "language": _bcp47(self.language),
            "description": self.description,
        }


@dataclass(frozen=True)
class ServiceConfig:
    runtime_dir: Path
    genie_data_dir: Path
    voices_file: Path
    voices: tuple[VoiceConfig, ...]
    default_voice_id: str
    api_key: str = ""
    max_text_chars: int = 2000

    @classmethod
    def from_env(cls) -> "ServiceConfig":
        plugin_root = Path(__file__).resolve().parents[2]
        runtime_dir = Path(
            os.environ.get("GENIE_TTS_RUNTIME_DIR", plugin_root / "runtime")
        ).expanduser().resolve()
        voices_file = Path(
            os.environ.get("GENIE_TTS_VOICES_FILE", runtime_dir / "voices.json")
        ).expanduser().resolve()
        genie_data_dir = Path(
            os.environ.get("GENIE_DATA_DIR", runtime_dir / "GenieData")
        ).expanduser().resolve()
        voices, default_voice = _load_voices(voices_file)
        try:
            max_chars = int(os.environ.get("GENIE_TTS_MAX_TEXT_CHARS", "2000"))
        except ValueError as exc:
            raise ConfigurationError("GENIE_TTS_MAX_TEXT_CHARS 必须是整数") from exc
        return cls(
            runtime_dir=runtime_dir,
            genie_data_dir=genie_data_dir,
            voices_file=voices_file,
            voices=voices,
            default_voice_id=default_voice,
            api_key=os.environ.get("GENIE_TTS_API_KEY", ""),
            max_text_chars=max(1, max_chars),
        )

    def voice(self, voice_id: str) -> VoiceConfig | None:
        return next((voice for voice in self.voices if voice.id == voice_id), None)

    def reload_voices(self) -> "ServiceConfig":
        voices, default_voice = _load_voices(self.voices_file)
        return replace(self, voices=voices, default_voice_id=default_voice)

    def problems(self) -> list[str]:
        problems: list[str] = []
        if not self.genie_data_dir.is_dir():
            problems.append(f"GenieData 不存在: {self.genie_data_dir}")
        if not self.voices:
            problems.append("没有选择音色，请先选择模型目录")
        if self.default_voice_id and self.voice(self.default_voice_id) is None:
            problems.append("default_voice_id 不在 voices 中")
        for voice in self.voices:
            problems.extend(voice.problems())
        return problems


def _load_voices(path: Path) -> tuple[tuple[VoiceConfig, ...], str]:
    if not path.is_file():
        return (), ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"无法读取音色配置 {path}: {exc}") from exc
    raw_voices = payload.get("voices") if isinstance(payload, dict) else None
    if not isinstance(raw_voices, list):
        raise ConfigurationError("voices.json 的 voices 必须是数组")
    base = path.parent
    voices: list[VoiceConfig] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_voices):
        if not isinstance(raw, dict):
            raise ConfigurationError(f"voices[{index}] 必须是对象")
        try:
            voice_id = str(raw["id"]).strip()
            name = str(raw.get("name") or voice_id).strip()
            language = str(raw.get("language") or "zh").strip()
            reference_language = str(
                raw.get("reference_language") or language
            ).strip()
            model_dir = _resolve(base, raw["model_dir"])
            reference_audio = _resolve(base, raw["reference_audio"])
            reference_text = str(raw["reference_text"])
        except (KeyError, TypeError) as exc:
            raise ConfigurationError(f"voices[{index}] 缺少必填字段") from exc
        if not voice_id or voice_id in seen:
            raise ConfigurationError(f"音色 id 为空或重复: {voice_id!r}")
        seen.add(voice_id)
        voices.append(VoiceConfig(
            id=voice_id,
            name=name,
            model_dir=model_dir,
            language=language,
            reference_audio=reference_audio,
            reference_text=reference_text,
            reference_language=reference_language,
            gender=str(raw["gender"]) if raw.get("gender") is not None else None,
            description=str(raw.get("description") or ""),
        ))
    default = str(payload.get("default_voice_id") or (voices[0].id if voices else ""))
    return tuple(voices), default


def _resolve(base: Path, value: object) -> Path:
    path = Path(str(value)).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def _bcp47(language: str) -> str:
    return {
        "zh": "zh-CN", "chinese": "zh-CN",
        "ja": "ja-JP", "jp": "ja-JP", "japanese": "ja-JP",
        "en": "en-US", "english": "en-US",
        "ko": "ko-KR", "kr": "ko-KR", "korean": "ko-KR",
    }.get(language.strip().lower(), language)
