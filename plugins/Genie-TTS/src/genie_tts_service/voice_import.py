"""Validated import of user-trained Genie ONNX voice bundles."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .config import ServiceConfig, VoiceConfig


MODEL_COMPONENTS = (
    "prompt_encoder",
    "t2s_encoder",
    "t2s_first_stage_decoder",
    "t2s_stage_decoder",
    "vits",
)
REFERENCE_SUFFIXES = {".wav", ".flac", ".ogg", ".aif", ".aiff"}
MODEL_ARTIFACT_SUFFIXES = {".onnx", ".bin", ".data"}


class VoiceImportError(ValueError):
    """The selected files do not form a usable Genie voice bundle."""


def import_voice(config: ServiceConfig, payload: object) -> tuple[ServiceConfig, VoiceConfig]:
    if not isinstance(payload, dict):
        raise VoiceImportError("导入参数必须是 JSON 对象")
    character_source = Path(str(payload.get("character_dir") or "")).expanduser().resolve()
    if not character_source.is_dir():
        raise VoiceImportError(f"角色目录不存在: {character_source}")
    voice_id = character_source.name.strip()
    _validate_voice_name(voice_id)
    model_source = character_source / "tts_models"
    _model_artifacts(model_source)
    reference_source, reference_text, reference_language = _reference(character_source)
    voice = VoiceConfig(
        id=voice_id,
        name=voice_id,
        model_dir=model_source,
        language="zh",
        reference_audio=reference_source,
        reference_text=reference_text,
        reference_language=reference_language,
        description="本次生成临时选择的 Genie ONNX 音色",
    )
    selected = replace(config, voices=(voice,), default_voice_id=voice_id)
    return selected, voice


def _model_artifacts(path: Path) -> tuple[Path, ...]:
    if not path.is_dir():
        raise VoiceImportError(f"ONNX 模型目录不存在: {path}")
    artifacts = tuple(
        item for item in path.iterdir()
        if item.is_file() and item.suffix.lower() in MODEL_ARTIFACT_SUFFIXES
    )
    onnx_names = [item.name.lower() for item in artifacts if item.suffix.lower() == ".onnx"]
    missing = [component for component in MODEL_COMPONENTS if not any(name.startswith(component) for name in onnx_names)]
    if missing:
        raise VoiceImportError("模型目录缺少 Genie 组件: " + ", ".join(missing))
    return artifacts


def _validate_voice_name(name: str) -> None:
    forbidden = set('<>:"/\\|?*')
    if not name or len(name) > 64 or any(char in forbidden or ord(char) < 32 for char in name):
        raise VoiceImportError("角色目录名无效；目录名将直接作为音色名称，最长 64 个字符")


def _reference(character_dir: Path) -> tuple[Path, str, str]:
    prompt_file = character_dir / "prompt_wav.json"
    prompt_dir = character_dir / "prompt_wav"
    if not prompt_file.is_file():
        raise VoiceImportError("角色目录缺少 prompt_wav.json")
    if not prompt_dir.is_dir():
        raise VoiceImportError("角色目录缺少 prompt_wav 文件夹")
    try:
        payload = json.loads(prompt_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VoiceImportError(f"prompt_wav.json 无法读取: {exc}") from exc
    if not isinstance(payload, dict) or not payload:
        raise VoiceImportError("prompt_wav.json 必须包含至少一条参考音频")
    entry = payload.get("Normal")
    if not isinstance(entry, dict):
        entry = next((item for item in payload.values() if isinstance(item, dict)), None)
    if not isinstance(entry, dict):
        raise VoiceImportError("prompt_wav.json 没有有效的参考音频记录")
    wav_name = str(entry.get("wav") or "").strip()
    text = str(entry.get("text") or "").strip()
    if not wav_name or not text:
        raise VoiceImportError("参考音频记录必须同时包含 wav 和准确文本 text")
    reference = (prompt_dir / wav_name).resolve()
    if not reference.is_relative_to(prompt_dir.resolve()) or not reference.is_file():
        raise VoiceImportError(f"prompt_wav 中找不到参考音频: {wav_name}")
    if reference.suffix.lower() not in REFERENCE_SUFFIXES:
        raise VoiceImportError("参考音频只支持 WAV、FLAC、OGG、AIFF")
    prefix = reference.name.split("_", 1)[0].lower()
    language = {"zh": "zh", "ja": "jp", "jp": "jp", "en": "en", "ko": "kr", "kr": "kr"}.get(prefix)
    if language is None:
        raise VoiceImportError("参考音频文件名必须以 zh_、jp_、en_ 或 kr_ 开头")
    return reference, text, language
