"""NVIDIA NeMo adapter for Parakeet TDT."""

from __future__ import annotations

import os
from pathlib import Path

from service import ApiError, EngineResult, TimelineSegment, TranscriptBlock, slice_wav


SUPPORTED_LANGUAGES = ["ja"]


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


class ParakeetEngine:
    def __init__(self) -> None:
        import torch
        import nemo.collections.asr as nemo_asr

        self.model_id = os.environ.get("ASR_MODEL_ID", "nvidia/parakeet-tdt_ctc-0.6b-ja")
        requested_device = os.environ.get("ASR_DEVICE", "auto").strip().lower()
        self.device = ("cuda" if torch.cuda.is_available() else "cpu") if requested_device == "auto" else requested_device
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("ASR_DEVICE 要求 CUDA，但当前 PyTorch 未检测到 CUDA")

        self.model = nemo_asr.models.ASRModel.from_pretrained(model_name=self.model_id)
        self.model.eval()
        self.model.to(self.device)
        if _env_bool("PARAKEET_LOCAL_ATTENTION", True):
            context = int(os.environ.get("PARAKEET_ATTENTION_CONTEXT", "256"))
            self.model.change_attention_model(
                self_attention_model="rel_pos_local_attn",
                att_context_size=[context, context],
            )

    @staticmethod
    def _outputs(value):
        if isinstance(value, tuple):
            return value[0]
        return value

    def _run(self, paths: list[Path]):
        value = self.model.transcribe(
            [str(path) for path in paths],
            batch_size=int(os.environ.get("PARAKEET_BATCH_SIZE", "1")),
            timestamps=True,
            verbose=False,
        )
        return self._outputs(value)

    @staticmethod
    def _text(hypothesis) -> str:
        return str(getattr(hypothesis, "text", hypothesis) or "").strip()

    @staticmethod
    def _requested_language(language: str | None) -> tuple[str, str]:
        normalized = (language or "auto").strip().lower()
        if normalized in {"", "auto", "ja", "ja-jp", "japanese"}:
            return "ja", "model_fixed_ja"
        raise ApiError(
            422,
            "UNSUPPORTED_LANGUAGE",
            f"日语 Parakeet 模型只支持日语，收到 {language}",
            details={"supported_languages": SUPPORTED_LANGUAGES},
        )

    def transcribe(
        self,
        wav_path: Path,
        duration_ms: int,
        segments: list[TimelineSegment] | None,
        language: str | None,
        work_dir: Path,
    ) -> EngineResult:
        output_language, language_source = self._requested_language(language)
        if segments is not None:
            paths: list[Path] = []
            for segment in segments:
                path = work_dir / f"segment-{segment.index:06d}.wav"
                slice_wav(wav_path, path, segment)
                paths.append(path)
            hypotheses = self._run(paths)
            blocks = [
                TranscriptBlock(segment.index, segment.start_ms, segment.end_ms, self._text(hypothesis))
                for segment, hypothesis in zip(segments, hypotheses, strict=True)
            ]
            text = "".join(block.text for block in blocks if block.text).strip()
        else:
            hypothesis = self._run([wav_path])[0]
            text = self._text(hypothesis)
            timestamp = getattr(hypothesis, "timestamp", None) or {}
            raw_segments = timestamp.get("segment", []) if isinstance(timestamp, dict) else []
            blocks = []
            previous_end = 0
            for raw in raw_segments:
                block_text = str(raw.get("segment") or raw.get("text") or "").strip()
                start_ms = max(previous_end, round(float(raw["start"]) * 1000))
                end_ms = min(duration_ms, round(float(raw["end"]) * 1000))
                if end_ms <= start_ms:
                    continue
                blocks.append(TranscriptBlock(len(blocks), start_ms, end_ms, block_text))
                previous_end = end_ms
            if text and not blocks:
                blocks = [TranscriptBlock(0, 0, duration_ms, text)]

        return EngineResult(
            language=output_language,
            text=text,
            blocks=blocks,
            metadata={
                "model": self.model_id,
                "runtime": "nemo",
                "language_source": language_source,
            },
        )


def load_engine() -> ParakeetEngine:
    return ParakeetEngine()
