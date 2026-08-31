"""Transformers adapter for Kotoba-Whisper v2.0."""

from __future__ import annotations

import os
import wave
from pathlib import Path

from service import ApiError, EngineResult, TimelineSegment, TranscriptBlock, slice_wav


SUPPORTED_LANGUAGES = ["ja"]


class KotobaWhisperEngine:
    def __init__(self) -> None:
        import torch
        from transformers import pipeline

        self.model_id = os.environ.get("ASR_MODEL_ID", "kotoba-tech/kotoba-whisper-v2.0")
        requested_device = os.environ.get("ASR_DEVICE", "auto").strip().lower()
        self.device = ("cuda:0" if torch.cuda.is_available() else "cpu") if requested_device == "auto" else requested_device
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("ASR_DEVICE 要求 CUDA，但当前 PyTorch 未检测到 CUDA")

        dtype_name = os.environ.get("KOTOBA_DTYPE", "auto").strip().lower()
        if dtype_name == "auto":
            if self.device.startswith("cuda"):
                dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            else:
                dtype = torch.float32
        else:
            dtype_map = {
                "float32": torch.float32,
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
            }
            if dtype_name not in dtype_map:
                raise RuntimeError("KOTOBA_DTYPE 必须是 auto/float32/float16/bfloat16")
            dtype = dtype_map[dtype_name]

        attention = os.environ.get("KOTOBA_ATTENTION", "sdpa" if self.device.startswith("cuda") else "eager")
        model_kwargs = {"attn_implementation": attention}
        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=self.model_id,
            torch_dtype=dtype,
            device=self.device,
            model_kwargs=model_kwargs,
            batch_size=int(os.environ.get("KOTOBA_BATCH_SIZE", "8")),
        )
        self.chunk_length_s = float(os.environ.get("KOTOBA_CHUNK_LENGTH_SECONDS", "0"))

    @staticmethod
    def _language(language: str | None) -> str:
        normalized = (language or "auto").strip().lower()
        if normalized in {"", "auto", "ja", "ja-jp", "japanese"}:
            return "ja"
        raise ApiError(
            422,
            "UNSUPPORTED_LANGUAGE",
            f"Kotoba-Whisper v2.0 只支持日语，收到 {language}",
            details={"supported_languages": SUPPORTED_LANGUAGES},
        )

    def _run(self, path: Path) -> dict:
        kwargs = {
            "return_timestamps": True,
            "generate_kwargs": {"language": "ja", "task": "transcribe"},
        }
        if self.chunk_length_s > 0:
            kwargs["chunk_length_s"] = self.chunk_length_s
        return self.pipe(self._read_wav(path), **kwargs)

    @staticmethod
    def _read_wav(path: Path) -> dict:
        """Read the normalized PCM WAV directly so Transformers never invokes ffmpeg."""
        import numpy as np

        try:
            with wave.open(str(path), "rb") as source:
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                sample_rate = source.getframerate()
                frames = source.readframes(source.getnframes())
        except (OSError, wave.Error) as exc:
            raise RuntimeError(f"无法读取标准化 WAV: {exc}") from exc
        if channels != 1 or sample_width != 2 or sample_rate <= 0:
            raise RuntimeError(
                "标准化 WAV 必须是单声道 16-bit PCM",
            )
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        return {"raw": samples, "sampling_rate": sample_rate}

    @staticmethod
    def _result_text(result: dict) -> str:
        return str(result.get("text") or "").strip()

    @staticmethod
    def _timestamp_blocks(result: dict, duration_ms: int) -> list[TranscriptBlock]:
        blocks: list[TranscriptBlock] = []
        previous_end = 0
        for raw in result.get("chunks") or []:
            timestamps = raw.get("timestamp") or (None, None)
            start_seconds, end_seconds = timestamps
            if start_seconds is None:
                start_ms = previous_end
            else:
                start_ms = max(previous_end, round(float(start_seconds) * 1000))
            if end_seconds is None:
                end_ms = duration_ms
            else:
                end_ms = min(duration_ms, round(float(end_seconds) * 1000))
            if end_ms <= start_ms:
                continue
            blocks.append(
                TranscriptBlock(
                    index=len(blocks),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=str(raw.get("text") or "").strip(),
                )
            )
            previous_end = end_ms
        return blocks

    def transcribe(
        self,
        wav_path: Path,
        duration_ms: int,
        segments: list[TimelineSegment] | None,
        language: str | None,
        work_dir: Path,
    ) -> EngineResult:
        output_language = self._language(language)
        if segments is not None:
            blocks: list[TranscriptBlock] = []
            for segment in segments:
                path = work_dir / f"segment-{segment.index:06d}.wav"
                slice_wav(wav_path, path, segment)
                result = self._run(path)
                blocks.append(
                    TranscriptBlock(
                        segment.index,
                        segment.start_ms,
                        segment.end_ms,
                        self._result_text(result),
                    )
                )
            text = "".join(block.text for block in blocks if block.text).strip()
        else:
            result = self._run(wav_path)
            text = self._result_text(result)
            blocks = self._timestamp_blocks(result, duration_ms)
            if text and not blocks:
                blocks = [TranscriptBlock(0, 0, duration_ms, text)]

        return EngineResult(
            language=output_language,
            text=text,
            blocks=blocks,
            metadata={
                "model": self.model_id,
                "runtime": "transformers",
                "language_source": "model_fixed_ja",
                "chunk_length_s": self.chunk_length_s,
            },
        )


def load_engine() -> KotobaWhisperEngine:
    return KotobaWhisperEngine()
