"""Normalize Genie output to the plugin's stable WAV contract."""

from __future__ import annotations

import audioop
import io
import wave


TARGET_RATE = 24000


class AudioFormatError(ValueError):
    """The generated file cannot be normalized safely."""


def normalize_wav(source: bytes) -> tuple[bytes, int]:
    try:
        with wave.open(io.BytesIO(source), "rb") as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            source_rate = reader.getframerate()
            frames = reader.readframes(reader.getnframes())
    except (EOFError, wave.Error) as exc:
        raise AudioFormatError(f"Genie 输出不是完整 WAV: {exc}") from exc
    if channels != 1 or width != 2 or source_rate <= 0 or not frames:
        raise AudioFormatError(
            f"Genie WAV 格式无效: channels={channels}, width={width}, rate={source_rate}"
        )
    if source_rate != TARGET_RATE:
        frames, _ = audioop.ratecv(frames, width, channels, source_rate, TARGET_RATE, None)
    if not frames:
        raise AudioFormatError("Genie 输出没有有效音频帧")
    target = io.BytesIO()
    with wave.open(target, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(TARGET_RATE)
        writer.writeframes(frames)
    duration_ms = max(1, round(len(frames) / 2 / TARGET_RATE * 1000))
    return target.getvalue(), duration_ms
