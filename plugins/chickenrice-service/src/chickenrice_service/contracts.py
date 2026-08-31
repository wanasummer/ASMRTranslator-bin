"""Stable request contracts shared by the HTTP and runner layers."""

from __future__ import annotations

import json
from dataclasses import dataclass


VAD_PROVIDERS = frozenset({"none", "external", "chickenrice"})
OUTPUT_LANGUAGES = frozenset({"ja", "zh"})


class ContractError(ValueError):
    """The caller supplied a request that violates the service contract."""


@dataclass(frozen=True)
class TimelineSegment:
    index: int
    start_ms: int
    end_ms: int

    def to_dict(self) -> dict:
        return {"index": self.index, "start_ms": self.start_ms, "end_ms": self.end_ms}


@dataclass(frozen=True)
class TranscriptionRequest:
    vad_provider: str = "none"
    output_language: str = "ja"
    segments: tuple[TimelineSegment, ...] = ()

    @property
    def task(self) -> str:
        return "transcribe" if self.output_language == "ja" else "translate"

    @property
    def timeline_source(self) -> str:
        return {
            "external": "external_vad",
            "chickenrice": "chickenrice_vad",
            "none": "asr",
        }[self.vad_provider]

    def to_dict(self) -> dict:
        return {
            "vad_provider": self.vad_provider,
            "output_language": self.output_language,
            "segments": [segment.to_dict() for segment in self.segments],
        }


def parse_request(
    vad_provider: str = "none",
    output_language: str = "ja",
    segments_json: str | None = None,
) -> TranscriptionRequest:
    vad = vad_provider.strip().lower()
    language = output_language.strip().lower()
    if vad not in VAD_PROVIDERS:
        raise ContractError(f"vad_provider 必须是: {', '.join(sorted(VAD_PROVIDERS))}")
    if language not in OUTPUT_LANGUAGES:
        raise ContractError(f"output_language 必须是: {', '.join(sorted(OUTPUT_LANGUAGES))}")

    raw_segments: object = []
    if segments_json and segments_json.strip():
        try:
            raw_segments = json.loads(segments_json)
        except json.JSONDecodeError as exc:
            raise ContractError(f"segments 不是有效 JSON: {exc.msg}") from exc
    if not isinstance(raw_segments, list):
        raise ContractError("segments 必须是 JSON 数组")

    segments: list[TimelineSegment] = []
    previous_end = -1
    for position, value in enumerate(raw_segments):
        if not isinstance(value, dict):
            raise ContractError(f"segments[{position}] 必须是对象")
        try:
            index = int(value.get("index", position))
            start_ms = int(value["start_ms"])
            end_ms = int(value["end_ms"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(
                f"segments[{position}] 需要整数 index/start_ms/end_ms"
            ) from exc
        if index < 0 or start_ms < 0 or end_ms <= start_ms:
            raise ContractError(f"segments[{position}] 时间范围或 index 无效")
        if start_ms < previous_end:
            raise ContractError("segments 必须按时间排序且不能重叠")
        segments.append(TimelineSegment(index, start_ms, end_ms))
        previous_end = end_ms

    if vad == "external" and not segments:
        raise ContractError("vad_provider=external 时必须提供 segments")
    if vad != "external" and segments:
        raise ContractError("只有 vad_provider=external 可以提供 segments")
    return TranscriptionRequest(vad, language, tuple(segments))
