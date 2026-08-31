"""Stable request validation for the standalone Genie plugin API."""

from __future__ import annotations

import re
from dataclasses import dataclass


CONTRACT_VERSION = 1
RATE_RE = re.compile(r"^[+-]\d{1,3}%$")
PITCH_RE = re.compile(r"^[+-]\d{1,4}Hz$")


class ContractError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class SynthesisRequest:
    segment_index: int
    text: str
    voice_id: str
    language: str
    request_id: str = ""
    speaker: str | None = None
    rate: str = "+0%"
    pitch: str = "+0Hz"


def parse_request(payload: object, max_text_chars: int) -> SynthesisRequest:
    if not isinstance(payload, dict):
        raise ContractError("INVALID_REQUEST", "请求体必须是 JSON 对象")
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise ContractError("INVALID_REQUEST", "contract_version 必须为 1")
    try:
        segment_index = int(payload["segment_index"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("INVALID_REQUEST", "segment_index 必须是非负整数") from exc
    if segment_index < 0:
        raise ContractError("INVALID_REQUEST", "segment_index 必须是非负整数")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ContractError("INVALID_REQUEST", "text 不能为空")
    if len(text) > max_text_chars:
        raise ContractError("TEXT_TOO_LONG", f"text 超过 {max_text_chars} 字符", 413)
    voice_id = str(payload.get("voice_id") or "").strip()
    if not voice_id:
        raise ContractError("INVALID_REQUEST", "voice_id 不能为空")
    language = str(payload.get("language") or "").strip()
    if language.lower() not in {"zh", "zh-cn", "chinese"}:
        raise ContractError("UNSUPPORTED_LANGUAGE", "Genie 插件当前只接收中文合成请求", 422)
    rate = str(payload.get("rate") or "+0%")
    pitch = str(payload.get("pitch") or "+0Hz")
    if not RATE_RE.fullmatch(rate) or rate != "+0%":
        raise ContractError("UNSUPPORTED_OPTION", "Genie 插件不原生支持非零 rate", 422)
    if not PITCH_RE.fullmatch(pitch) or pitch != "+0Hz":
        raise ContractError("UNSUPPORTED_OPTION", "Genie 插件不支持非零 pitch", 422)
    output = payload.get("output")
    required_output = {
        "container": "wav", "codec": "pcm_s16le",
        "sample_rate_hz": 24000, "channels": 1,
    }
    if output != required_output:
        raise ContractError("UNSUPPORTED_OUTPUT", "只支持 24kHz 单声道 pcm_s16le WAV", 415)
    return SynthesisRequest(
        segment_index=segment_index,
        text=text,
        voice_id=voice_id,
        language=language,
        request_id=str(payload.get("request_id") or ""),
        speaker=str(payload["speaker"]) if payload.get("speaker") is not None else None,
        rate=rate,
        pitch=pitch,
    )


def error_body(code: str, message: str, retryable: bool, details: dict | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details or {},
        }
    }
