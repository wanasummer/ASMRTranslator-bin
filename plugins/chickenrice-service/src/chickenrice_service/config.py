"""Service configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .contracts import TranscriptionRequest
from .gpu_runtime import configure_gpu_runtime, inspect_gpu_runtime


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ServiceConfig:
    runtime_dir: Path
    work_dir: Path
    upstream_dir: Path
    japanese_model_dir: Path
    chinese_model_dir: Path
    generation_config: Path
    executable: Path | None
    python_executable: Path
    device: str
    compute_type: str
    api_key: str
    max_upload_bytes: int
    job_ttl_seconds: int
    command_timeout_seconds: int
    keep_failed_artifacts: bool

    @classmethod
    def from_env(cls) -> "ServiceConfig":
        runtime = Path(os.environ.get("CHICKENRICE_RUNTIME_DIR", "runtime")).resolve()
        executable_text = os.environ.get("CHICKENRICE_EXECUTABLE", "").strip()
        device = os.environ.get("CHICKENRICE_DEVICE", "cuda").strip().lower()
        configure_gpu_runtime(device)
        default_compute = "int8_float16" if device in {"cuda", "amd", "rocm", "hip"} else "int8"
        return cls(
            runtime_dir=runtime,
            work_dir=Path(os.environ.get("CHICKENRICE_WORK_DIR", runtime / "jobs")).resolve(),
            upstream_dir=Path(os.environ.get("CHICKENRICE_UPSTREAM_DIR", runtime / "upstream")).resolve(),
            japanese_model_dir=Path(
                os.environ.get("CHICKENRICE_JA_MODEL_DIR", runtime / "models" / "japanese-asr")
            ).resolve(),
            chinese_model_dir=Path(
                os.environ.get(
                    "CHICKENRICE_ZH_MODEL_DIR",
                    os.environ.get("CHICKENRICE_MODEL_DIR", runtime / "models" / "chinese-translate"),
                )
            ).resolve(),
            generation_config=Path(
                os.environ.get("CHICKENRICE_GENERATION_CONFIG", runtime / "generation_config.json5")
            ).resolve(),
            executable=Path(executable_text).resolve() if executable_text else None,
            python_executable=Path(os.environ.get("CHICKENRICE_PYTHON", os.sys.executable)).resolve(),
            device=device,
            compute_type=os.environ.get("CHICKENRICE_COMPUTE_TYPE", default_compute).strip(),
            api_key=os.environ.get("CHICKENRICE_API_KEY", "").strip(),
            max_upload_bytes=int(os.environ.get("CHICKENRICE_MAX_UPLOAD_BYTES", str(4 * 1024**3))),
            job_ttl_seconds=int(os.environ.get("CHICKENRICE_JOB_TTL_SECONDS", str(24 * 3600))),
            command_timeout_seconds=int(os.environ.get("CHICKENRICE_TIMEOUT_SECONDS", str(6 * 3600))),
            keep_failed_artifacts=_env_bool("CHICKENRICE_KEEP_FAILED_ARTIFACTS", True),
        )

    @staticmethod
    def _model_ready(path: Path) -> bool:
        return path.is_dir() and (path / "model.bin").is_file()

    def _installed_capability_status(self) -> dict[str, bool]:
        vad_files = all(
            (self.runtime_dir / "models" / filename).is_file()
            for filename in ("whisper_vad.onnx", "whisper_vad_metadata.json")
        )
        upstream_ready = self.executable is not None and self.executable.is_file()
        if self.executable is None:
            upstream_ready = (self.upstream_dir / "infer.py").is_file()
        return {
            "japanese_asr": self._model_ready(self.japanese_model_dir),
            "chinese_translation": self._model_ready(self.chinese_model_dir),
            "chickenrice_vad": vad_files and upstream_ready and self.generation_config.is_file(),
        }

    def runtime_status(self) -> dict:
        return inspect_gpu_runtime(self.device)

    def capability_status(self) -> dict[str, bool]:
        installed = self._installed_capability_status()
        runtime_ready = bool(self.runtime_status()["available"])
        return {name: ready and runtime_ready for name, ready in installed.items()}

    def validate(self) -> list[str]:
        """Validate the complete runtime installed by every supported installer."""
        problems: list[str] = []
        capabilities = self._installed_capability_status()
        if not capabilities["japanese_asr"]:
            problems.append(f"日语 ASR 核心模型未安装或不完整: {self.japanese_model_dir}")
        if not capabilities["chinese_translation"]:
            problems.append(f"中文字幕模型未安装或不完整: {self.chinese_model_dir}")
        if not capabilities["chickenrice_vad"]:
            problems.append("海南鸡 VAD 运行时未安装或不完整")
        problems.extend(self.runtime_status()["problems"])
        if self.max_upload_bytes <= 0:
            problems.append("CHICKENRICE_MAX_UPLOAD_BYTES 必须大于 0")
        return problems

    def validate_request(self, request: TranscriptionRequest) -> list[str]:
        del request  # Runtime installation is complete; selection is request-scoped only.
        return self.validate()
