"""Replaceable ASR runners and VAD-provider routing."""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .config import ServiceConfig
from .contracts import TranscriptionRequest
from .subtitles import SubtitleBlock, parse_vtt, write_vtt


ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class RunResult:
    vtt_path: Path
    blocks: list[SubtitleBlock]
    log_path: Path
    language: str
    source: str
    timeline_source: str


class SubtitleRunner(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        output_dir: Path,
        request: TranscriptionRequest,
        progress: ProgressCallback,
    ) -> RunResult: ...


class WhisperCoreRunner:
    """Japanese ASR core, independent from ChickenRice VAD and translation."""

    def __init__(self, config: ServiceConfig, model_factory=None):
        self.config = config
        self._model_factory = model_factory
        self._models: dict[str, object] = {}
        self._model_lock = threading.Lock()

    def _model(self, language: str):
        with self._model_lock:
            if language in self._models:
                return self._models[language]
            factory = self._model_factory
            if factory is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise RuntimeError("缺少 faster-whisper 推理依赖，请重新运行安装器") from exc
                factory = WhisperModel
            path = self.config.japanese_model_dir if language == "ja" else self.config.chinese_model_dir
            device = "cuda" if self.config.device in {"amd", "rocm", "hip"} else self.config.device
            model = factory(str(path), device=device, compute_type=self.config.compute_type)
            self._models[language] = model
            return model

    @staticmethod
    def _texts(segments) -> str:
        return "".join(str(segment.text).strip() for segment in segments).strip()

    def transcribe(
        self,
        audio_path: Path,
        output_dir: Path,
        request: TranscriptionRequest,
        progress: ProgressCallback,
    ) -> RunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "asr.log"
        model = self._model(request.output_language)
        common = {
            "language": "ja",
            "task": request.task,
            "vad_filter": False,
            "condition_on_previous_text": False,
        }
        blocks: list[SubtitleBlock] = []
        if request.vad_provider == "external":
            total = len(request.segments)
            for position, authored in enumerate(request.segments):
                clip = [authored.start_ms / 1000, authored.end_ms / 1000]
                fragments, _info = model.transcribe(str(audio_path), clip_timestamps=clip, **common)
                blocks.append(
                    SubtitleBlock(
                        authored.index,
                        authored.start_ms,
                        authored.end_ms,
                        self._texts(fragments),
                    )
                )
                progress(
                    0.1 + 0.8 * ((position + 1) / total),
                    f"已识别 {position + 1}/{total} 个 VAD 切片",
                )
        else:
            fragments, _info = model.transcribe(str(audio_path), **common)
            for fragment in fragments:
                text = str(fragment.text).strip()
                start_ms = max(0, round(float(fragment.start) * 1000))
                end_ms = max(start_ms + 1, round(float(fragment.end) * 1000))
                if text:
                    blocks.append(SubtitleBlock(len(blocks), start_ms, end_ms, text))
            progress(0.9, f"已生成 {len(blocks)} 个 ASR 字幕块")

        vtt_path = write_vtt(output_dir / "subtitles.vtt", blocks)
        log_path.write_text(
            f"mode={request.output_language} vad={request.vad_provider} blocks={len(blocks)}\n",
            encoding="utf-8",
        )
        return RunResult(
            vtt_path,
            blocks,
            log_path,
            request.output_language,
            "chickenrice-ja-asr" if request.output_language == "ja" else "chickenrice-zh-translate",
            request.timeline_source,
        )


class ChickenRiceCliRunner:
    """Optional adapter using the upstream ChickenRice ASMR VAD pipeline."""

    def __init__(self, config: ServiceConfig):
        self.config = config
        self._cwd = config.runtime_dir

    def _command(self, audio_path: Path, output_dir: Path, request: TranscriptionRequest) -> list[str]:
        if self.config.executable:
            prefix = [str(self.config.executable)]
            self._cwd = self.config.executable.parent
        else:
            prefix = [str(self.config.python_executable), str(self.config.upstream_dir / "infer.py")]
            self._cwd = self.config.runtime_dir
        model_dir = {
            "ja": self.config.japanese_model_dir,
            "zh": self.config.chinese_model_dir,
        }[request.output_language]
        return prefix + [
            f"--model_name_or_path={model_dir}",
            f"--device={self.config.device}",
            f"--compute_type={self.config.compute_type}",
            "--overwrite",
            f"--task={request.task}",
            "--sub_formats=vtt",
            f"--output_dir={output_dir}",
            f"--generation_config={self.config.generation_config}",
            str(audio_path),
        ]

    def transcribe(
        self,
        audio_path: Path,
        output_dir: Path,
        request: TranscriptionRequest,
        progress: ProgressCallback,
    ) -> RunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "chickenrice.log"
        command = self._command(audio_path, output_dir, request)
        env = os.environ.copy()
        upstream_src = str(self.config.upstream_dir / "src")
        env["PYTHONPATH"] = upstream_src + os.pathsep + env.get("PYTHONPATH", "")
        progress(0.1, "海南鸡 VAD 与识别任务已启动")
        try:
            completed = subprocess.run(
                command,
                cwd=self._cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.command_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            log_path.write_text((exc.stdout or "") + "\n" + (exc.stderr or ""), encoding="utf-8")
            raise RuntimeError(f"海南鸡推理超过 {self.config.command_timeout_seconds} 秒") from exc
        log_path.write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout)[-1500:]
            raise RuntimeError(f"海南鸡返回退出码 {completed.returncode}: {tail}")
        candidates = sorted(output_dir.glob("*.vtt"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        if not candidates:
            raise RuntimeError("海南鸡执行成功但没有生成 VTT")
        blocks = parse_vtt(candidates[0])
        if not blocks:
            raise RuntimeError(
                "海南鸡生成了 VTT，但其中没有可解析的非空字幕块。"
                f"请检查音频、VAD 输出和日志：{log_path}"
            )
        progress(0.95, f"已生成 {len(blocks)} 个字幕块")
        return RunResult(
            candidates[0],
            blocks,
            log_path,
            request.output_language,
            "chickenrice-vad",
            request.timeline_source,
        )


class RoutedSubtitleRunner:
    """Registry-backed VAD provider dispatcher."""

    def __init__(self, providers: dict[str, SubtitleRunner]):
        self.providers = dict(providers)

    def transcribe(
        self,
        audio_path: Path,
        output_dir: Path,
        request: TranscriptionRequest,
        progress: ProgressCallback,
    ) -> RunResult:
        try:
            provider = self.providers[request.vad_provider]
        except KeyError as exc:
            raise RuntimeError(f"未注册 VAD provider: {request.vad_provider}") from exc
        return provider.transcribe(audio_path, output_dir, request, progress)


def create_runner(config: ServiceConfig) -> SubtitleRunner:
    core = WhisperCoreRunner(config)
    return RoutedSubtitleRunner(
        {
            "none": core,
            "external": core,
            "chickenrice": ChickenRiceCliRunner(config),
        }
    )
