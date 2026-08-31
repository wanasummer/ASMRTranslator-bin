"""HTTP contract, audio normalization, and model lifecycle for a common ASR service."""

from __future__ import annotations

import hmac
import json
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from fastapi import Depends, FastAPI, File, Form, Header, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class TimelineSegment:
    index: int
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class TranscriptBlock:
    index: int
    start_ms: int
    end_ms: int
    text: str

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text.strip(),
            "skip_tts": False,
        }


@dataclass(frozen=True)
class EngineResult:
    language: str
    text: str
    blocks: list[TranscriptBlock]
    metadata: dict


class ASREngine(Protocol):
    model_id: str
    device: str

    def transcribe(
        self,
        wav_path: Path,
        duration_ms: int,
        segments: list[TimelineSegment] | None,
        language: str | None,
        work_dir: Path,
    ) -> EngineResult: ...


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def payload(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "details": self.details,
            }
        }


class ModelHolder:
    """Load one GPU model in the background and serialize inference calls."""

    def __init__(self, loader: Callable[[], ASREngine], ffmpeg_bin: str) -> None:
        self._loader = loader
        self._ffmpeg_bin = ffmpeg_bin
        self._engine: ASREngine | None = None
        self._error: str | None = None
        self._started = False
        self._state_lock = threading.Lock()
        self.inference_lock = threading.Lock()

    def start(self) -> None:
        with self._state_lock:
            if self._started:
                return
            self._started = True
        threading.Thread(target=self._load, name="asr-model-loader", daemon=True).start()

    def _load(self) -> None:
        try:
            if not shutil.which(self._ffmpeg_bin):
                raise RuntimeError(f"找不到 ffmpeg 可执行文件: {self._ffmpeg_bin}")
            engine = self._loader()
        except Exception as exc:  # startup boundary: expose a safe readiness reason
            with self._state_lock:
                self._error = f"{type(exc).__name__}: {exc}"
            return
        with self._state_lock:
            self._engine = engine
            self._error = None

    def status(self) -> tuple[ASREngine | None, str | None]:
        with self._state_lock:
            return self._engine, self._error

    def require(self) -> ASREngine:
        engine, error = self.status()
        if engine is None:
            message = error or "模型正在加载"
            raise ApiError(503, "SERVICE_NOT_READY", message, retryable=True)
        return engine


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_segments(raw: str | None, duration_ms: int) -> list[TimelineSegment] | None:
    if raw is None or not raw.strip():
        return None
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(422, "INVALID_SEGMENTS", f"segments 不是有效 JSON: {exc.msg}") from exc
    if not isinstance(values, list) or not values:
        raise ApiError(422, "INVALID_SEGMENTS", "segments 必须是非空 JSON 数组")

    parsed: list[TimelineSegment] = []
    previous_end = 0
    for position, value in enumerate(values):
        if not isinstance(value, dict):
            raise ApiError(422, "INVALID_SEGMENTS", f"segments[{position}] 必须是对象")
        index = value.get("index")
        start_ms = value.get("start_ms")
        end_ms = value.get("end_ms")
        if not all(_is_int(item) for item in (index, start_ms, end_ms)):
            raise ApiError(422, "INVALID_SEGMENTS", f"segments[{position}] 的字段必须是整数")
        if index != position:
            raise ApiError(422, "INVALID_SEGMENTS", "index 必须从 0 连续递增")
        if start_ms < 0 or end_ms <= start_ms:
            raise ApiError(422, "INVALID_SEGMENTS", f"segments[{position}] 时间范围无效")
        if position and start_ms < previous_end:
            raise ApiError(422, "INVALID_SEGMENTS", "segments 必须按时间排序且不能重叠")
        if end_ms > duration_ms:
            raise ApiError(
                422,
                "INVALID_SEGMENTS",
                f"segments[{position}].end_ms 超过音频时长",
                details={"segment_index": position, "duration_ms": duration_ms},
            )
        parsed.append(TimelineSegment(index, start_ms, end_ms))
        previous_end = end_ms
    return parsed


def save_upload(upload: UploadFile, target: Path, max_bytes: int) -> None:
    size = 0
    with target.open("wb") as output:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ApiError(
                    413,
                    "AUDIO_TOO_LARGE",
                    f"音频超过上传限制 {max_bytes} 字节",
                )
            output.write(chunk)
    if size == 0:
        raise ApiError(400, "INVALID_REQUEST", "上传音频为空")


def normalize_audio(source: Path, target: Path, ffmpeg_bin: str, timeout: int) -> int:
    command = [
        ffmpeg_bin,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ApiError(504, "ASR_TIMEOUT", "音频解码超时", retryable=True) from exc
    except OSError as exc:
        raise ApiError(503, "SERVICE_NOT_READY", f"无法启动 ffmpeg: {exc}", retryable=True) from exc
    if completed.returncode != 0 or not target.is_file():
        reason = completed.stderr.strip()[-500:] or "ffmpeg 无法解码音频"
        raise ApiError(415, "UNSUPPORTED_AUDIO", reason)
    try:
        with wave.open(str(target), "rb") as wav:
            duration_ms = round(wav.getnframes() * 1000 / wav.getframerate())
    except (OSError, wave.Error) as exc:
        raise ApiError(415, "UNSUPPORTED_AUDIO", f"解码结果无效: {exc}") from exc
    if duration_ms <= 0:
        raise ApiError(415, "UNSUPPORTED_AUDIO", "音频时长为 0")
    return duration_ms


def slice_wav(source: Path, target: Path, segment: TimelineSegment) -> None:
    with wave.open(str(source), "rb") as reader:
        sample_rate = reader.getframerate()
        start_frame = round(segment.start_ms * sample_rate / 1000)
        end_frame = round(segment.end_ms * sample_rate / 1000)
        reader.setpos(start_frame)
        frames = reader.readframes(end_frame - start_frame)
        params = reader.getparams()
    with wave.open(str(target), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames)


def create_app(
    loader: Callable[[], ASREngine],
    service_name: str,
    languages: list[str],
) -> FastAPI:
    ffmpeg_bin = os.environ.get("ASR_FFMPEG_BIN", "ffmpeg")
    api_key = os.environ.get("ASR_API_KEY", "").strip()
    max_upload_bytes = int(os.environ.get("ASR_MAX_UPLOAD_BYTES", str(1024**3)))
    ffmpeg_timeout = int(os.environ.get("ASR_FFMPEG_TIMEOUT_SECONDS", "1800"))
    holder = ModelHolder(loader, ffmpeg_bin)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        holder.start()
        yield

    app = FastAPI(title=f"{service_name} Common ASR", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(ApiError)
    async def api_error_handler(_, exc: ApiError) -> JSONResponse:
        return JSONResponse(exc.payload(), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_, exc: RequestValidationError) -> JSONResponse:
        error = ApiError(400, "INVALID_REQUEST", "请求字段无效", details={"errors": exc.errors()})
        return JSONResponse(error.payload(), status_code=400)

    def authorize(authorization: str | None = Header(default=None)) -> None:
        if not api_key:
            return
        expected = f"Bearer {api_key}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise ApiError(401, "UNAUTHORIZED", "Token 缺失或无效")

    @app.get("/health")
    def health(_: None = Depends(authorize)) -> JSONResponse:
        engine, load_error = holder.status()
        if engine is None:
            error = ApiError(
                503,
                "SERVICE_NOT_READY",
                load_error or "模型正在加载",
                retryable=True,
            )
            return JSONResponse(error.payload(), status_code=503)
        return JSONResponse({
            "status": "ok",
            "contract_version": 1,
            "service": service_name,
            "ready": True,
            "capabilities": {
                "languages": languages,
                "timestamps": True,
                "external_segments": True,
                "max_upload_bytes": max_upload_bytes,
            },
            "runtime": {"model": engine.model_id, "device": engine.device},
        })

    @app.post("/job")
    def job(
        response: Response,
        audio: UploadFile = File(...),
        language: str | None = Form(default=None),
        segments: str | None = Form(default=None),
        request_id: str | None = Form(default=None),
        _: None = Depends(authorize),
    ) -> dict:
        engine = holder.require()
        if request_id:
            response.headers["X-Request-ID"] = request_id
        with tempfile.TemporaryDirectory(prefix="common-asr-") as temporary:
            work_dir = Path(temporary)
            source_path = work_dir / "upload.bin"
            wav_path = work_dir / "audio-16k-mono.wav"
            save_upload(audio, source_path, max_upload_bytes)
            duration_ms = normalize_audio(source_path, wav_path, ffmpeg_bin, ffmpeg_timeout)
            parsed_segments = parse_segments(segments, duration_ms)
            try:
                with holder.inference_lock:
                    result = engine.transcribe(
                        wav_path,
                        duration_ms,
                        parsed_segments,
                        language,
                        work_dir,
                    )
            except ApiError:
                raise
            except Exception as exc:
                raise ApiError(500, "ASR_FAILED", f"ASR 推理失败: {type(exc).__name__}: {exc}") from exc
        blocks = [block.to_dict() for block in result.blocks]
        return {
            "contract_version": 1,
            "stage": "asr",
            "language": result.language,
            "source": engine.model_id,
            "timeline_source": "external_segments" if parsed_segments is not None else "asr",
            "duration_ms": duration_ms,
            "text": result.text.strip(),
            "blocks": blocks,
            "metadata": result.metadata,
        }

    return app
