"""Single-worker persistent artifact queue for long ASR jobs."""

from __future__ import annotations

import json
import queue
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import BinaryIO

from .config import ServiceConfig
from .contracts import TranscriptionRequest, parse_request
from .runner import SubtitleRunner


@dataclass
class Job:
    id: str
    status: str
    filename: str
    created_at: float
    updated_at: float
    progress: float = 0.0
    message: str = "等待处理"
    error: str | None = None
    block_count: int = 0
    vad_provider: str = "none"
    output_language: str = "ja"
    segments: list[dict] = field(default_factory=list)
    directory: Path = field(default=Path("."), repr=False)

    def public(self) -> dict:
        value = asdict(self)
        value.pop("directory", None)
        return value


class JobManager:
    def __init__(self, config: ServiceConfig, runner: SubtitleRunner):
        self.config = config
        self.runner = runner
        self.config.work_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._load_existing()
        self._worker = threading.Thread(target=self._work, name="chickenrice-worker", daemon=True)
        self._worker.start()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def submit(self, filename: str, source: BinaryIO, request: TranscriptionRequest) -> Job:
        self.cleanup_expired()
        job_id = uuid.uuid4().hex
        safe_name = Path(filename or "audio.bin").name
        directory = self.config.work_dir / job_id
        directory.mkdir(parents=True, exist_ok=False)
        audio_path = directory / safe_name
        size = 0
        with audio_path.open("wb") as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.config.max_upload_bytes:
                    target.close()
                    shutil.rmtree(directory, ignore_errors=True)
                    raise ValueError(f"上传文件超过限制 {self.config.max_upload_bytes} 字节")
                target.write(chunk)
        if size == 0:
            shutil.rmtree(directory, ignore_errors=True)
            raise ValueError("上传文件为空")
        now = time.time()
        job = Job(
            job_id,
            "queued",
            safe_name,
            now,
            now,
            vad_provider=request.vad_provider,
            output_language=request.output_language,
            segments=[segment.to_dict() for segment in request.segments],
            directory=directory,
        )
        with self._lock:
            self._jobs[job_id] = job
            self._persist(job)
        self._queue.put(job_id)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def result(self, job_id: str) -> dict | None:
        job = self.get(job_id)
        if not job or job.status != "succeeded":
            return None
        path = job.directory / "result.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def vtt_path(self, job_id: str) -> Path | None:
        result = self.result(job_id)
        if not result:
            return None
        path = self.get(job_id).directory / result["vtt_filename"]  # type: ignore[union-attr]
        return path if path.is_file() else None

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status == "running":
                return False
            self._jobs.pop(job_id, None)
        shutil.rmtree(job.directory, ignore_errors=True)
        return True

    def cleanup_expired(self) -> None:
        cutoff = time.time() - self.config.job_ttl_seconds
        with self._lock:
            expired = [job.id for job in self._jobs.values() if job.updated_at < cutoff and job.status != "running"]
        for job_id in expired:
            self.delete(job_id)

    def _update(self, job: Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time.time()
            self._persist(job)

    def _persist(self, job: Job) -> None:
        (job.directory / "job.json").write_text(
            json.dumps(job.public(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load_existing(self) -> None:
        for state_path in self.config.work_dir.glob("*/job.json"):
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
                directory = state_path.parent
                job = Job(
                    id=str(payload["id"]),
                    status=str(payload["status"]),
                    filename=str(payload["filename"]),
                    created_at=float(payload["created_at"]),
                    updated_at=float(payload["updated_at"]),
                    progress=float(payload.get("progress", 0.0)),
                    message=str(payload.get("message", "")),
                    error=payload.get("error"),
                    block_count=int(payload.get("block_count", 0)),
                    vad_provider=str(payload.get("vad_provider", "none")),
                    output_language=str(payload.get("output_language", "ja")),
                    segments=list(payload.get("segments", [])),
                    directory=directory,
                )
                if job.status in {"queued", "running"}:
                    job.status = "failed"
                    job.error = "服务重启中断了任务，请重新提交"
                    job.message = "任务已中断"
                    job.updated_at = time.time()
                    self._persist(job)
                self._jobs[job.id] = job
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue

    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            job = self.get(job_id)
            if not job:
                continue
            audio_path = job.directory / job.filename
            output_dir = job.directory / "output"
            request = parse_request(
                job.vad_provider,
                job.output_language,
                json.dumps(job.segments, ensure_ascii=False),
            )

            def progress(value: float, message: str) -> None:
                self._update(job, progress=max(0.0, min(0.99, value)), message=message)

            self._update(job, status="running", progress=0.05, message="正在生成字幕")
            try:
                run_result = self.runner.transcribe(audio_path, output_dir, request, progress)
                final_vtt = job.directory / "subtitles.vtt"
                shutil.copy2(run_result.vtt_path, final_vtt)
                payload = {
                    "job_id": job.id,
                    "contract_version": 1,
                    "stage": "asr",
                    "language": run_result.language,
                    "source": run_result.source,
                    "vad_provider": request.vad_provider,
                    "timeline_source": run_result.timeline_source,
                    "vtt_filename": final_vtt.name,
                    "blocks": [block.to_dict() for block in run_result.blocks],
                }
                (job.directory / "result.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                self._update(
                    job,
                    status="succeeded",
                    progress=1.0,
                    message="字幕生成完成",
                    block_count=len(run_result.blocks),
                )
            except Exception as exc:  # worker boundary: persist a user-facing failure
                self._update(job, status="failed", error=str(exc), message="字幕生成失败")
                if not self.config.keep_failed_artifacts:
                    shutil.rmtree(output_dir, ignore_errors=True)
