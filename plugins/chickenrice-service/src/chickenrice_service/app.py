"""FastAPI application factory."""

from __future__ import annotations

import hmac

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from . import __version__
from .config import ServiceConfig
from .contracts import ContractError, parse_request
from .jobs import JobManager
from .runner import SubtitleRunner, create_runner


def create_app(config: ServiceConfig | None = None, runner: SubtitleRunner | None = None) -> FastAPI:
    cfg = config or ServiceConfig.from_env()
    manager = JobManager(cfg, runner or create_runner(cfg))
    app = FastAPI(title="ChickenRice Subtitle Service", version=__version__)
    app.state.config = cfg
    app.state.jobs = manager

    def authorize(authorization: str | None = Header(default=None)) -> None:
        if not cfg.api_key:
            return
        expected = f"Bearer {cfg.api_key}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key 无效")

    @app.get("/health")
    def health(_: None = Depends(authorize)) -> dict:
        problems = cfg.validate()
        return {
            "status": "ready" if not problems else "not_ready",
            "version": __version__,
            "device": cfg.device,
            "compute_type": cfg.compute_type,
            "queue_size": manager.queue_size,
            "capabilities": cfg.capability_status(),
            "runtime": cfg.runtime_status(),
            "problems": problems,
        }

    @app.post("/v1/jobs", status_code=status.HTTP_202_ACCEPTED)
    def create_job(
        audio: UploadFile = File(...),
        vad_provider: str = Form("none"),
        output_language: str = Form("ja"),
        segments: str | None = Form(None),
        _: None = Depends(authorize),
    ) -> dict:
        try:
            request = parse_request(vad_provider, output_language, segments)
        except ContractError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        problems = cfg.validate_request(request)
        if problems:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=problems)
        try:
            return manager.submit(audio.filename or "audio.bin", audio.file, request).public()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc

    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str, _: None = Depends(authorize)) -> dict:
        job = manager.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
        return job.public()

    @app.get("/v1/jobs/{job_id}/result")
    def get_result(job_id: str, _: None = Depends(authorize)) -> dict:
        job = manager.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
        if job.status != "succeeded":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=job.public())
        return manager.result(job_id) or {}

    @app.get("/v1/jobs/{job_id}/subtitles.vtt")
    def get_vtt(job_id: str, _: None = Depends(authorize)) -> FileResponse:
        path = manager.vtt_path(job_id)
        if not path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字幕尚不可用")
        return FileResponse(path, media_type="text/vtt; charset=utf-8", filename="subtitles.vtt")

    @app.delete("/v1/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_job(job_id: str, _: None = Depends(authorize)) -> None:
        job = manager.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
        if job.status == "running":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="运行中的任务不能删除")
        manager.delete(job_id)

    return app
