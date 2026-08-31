"""Strict, dependency-free WebVTT parsing for service results."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path


_TIMING = re.compile(
    r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}[.,]\d{1,3})\s+-->\s+"
    r"(?P<end>(?:\d{2}:)?\d{2}:\d{2}[.,]\d{1,3})"
)


@dataclass(frozen=True)
class SubtitleBlock:
    index: int
    start_ms: int
    end_ms: int
    text: str
    skip_tts: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _timestamp_ms(value: str) -> int:
    parts = value.replace(",", ".").split(":")
    hours, minutes, seconds = ("0", *parts) if len(parts) == 2 else parts
    whole, millis = seconds.split(".")
    millis = millis.ljust(3, "0")
    return ((int(hours) * 60 + int(minutes)) * 60 + int(whole)) * 1000 + int(millis)


def parse_vtt_text(content: str) -> list[SubtitleBlock]:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[SubtitleBlock] = []
    cursor = 0
    while cursor < len(lines):
        match = _TIMING.search(lines[cursor])
        if not match:
            cursor += 1
            continue
        start_ms = _timestamp_ms(match.group("start"))
        end_ms = _timestamp_ms(match.group("end"))
        cursor += 1
        text_lines: list[str] = []
        while cursor < len(lines) and lines[cursor].strip():
            text_lines.append(lines[cursor].strip())
            cursor += 1
        text = " ".join(text_lines).strip()
        if text and end_ms > start_ms:
            blocks.append(SubtitleBlock(len(blocks), start_ms, end_ms, text))
    return blocks


def parse_vtt(path: Path) -> list[SubtitleBlock]:
    return parse_vtt_text(path.read_text(encoding="utf-8-sig"))


def _timestamp(value_ms: int) -> str:
    hours, remainder = divmod(value_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def write_vtt(path: Path, blocks: list[SubtitleBlock]) -> Path:
    """Persist non-empty blocks as UTF-8 VTT; JSON remains the canonical result."""
    lines = ["WEBVTT", ""]
    for block in blocks:
        if not block.text.strip():
            continue
        lines.extend(
            [
                str(block.index),
                f"{_timestamp(block.start_ms)} --> {_timestamp(block.end_ms)}",
                block.text.strip(),
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
