"""FastAPI implementation of the standalone Genie plugin API."""

from __future__ import annotations

import hmac

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from . import __version__
from .config import ConfigurationError, ServiceConfig
from .contracts import ContractError, error_body, parse_request
from .engine import EngineError, GenieEngine
from .voice_import import VoiceImportError, import_voice


def create_app(
    config: ServiceConfig | None = None,
    engine: GenieEngine | None = None,
) -> FastAPI:
    cfg = config or ServiceConfig.from_env()
    runtime = engine or GenieEngine(cfg)
    app = FastAPI(title="Genie TTS Engine Plugin", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.state.config = cfg
    app.state.engine = runtime

    def current_config() -> ServiceConfig:
        return getattr(runtime, "config", app.state.config)

    def authorize(authorization: str | None = Header(default=None)) -> None:
        current = current_config()
        if not current.api_key:
            return
        expected = f"Bearer {current.api_key}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise ContractError("UNAUTHORIZED", "API key 无效", 401)

    @app.exception_handler(ContractError)
    async def contract_error(_: Request, exc: ContractError) -> JSONResponse:
        return JSONResponse(
            error_body(exc.code, str(exc), exc.status_code in {429, 503, 504}),
            status_code=exc.status_code,
        )

    @app.get("/health")
    def health(_: None = Depends(authorize)) -> Response:
        current = current_config()
        ready, problems = runtime.health()
        payload = {
            "status": "ok" if ready else "error",
            "contract_version": 1,
            "service": "genie-tts-service",
            "ready": ready,
            "version": __version__,
            "capabilities": {
                "languages": ["zh-CN"],
                "voice_catalog": True,
                "rate": False,
                "pitch": False,
                "output": {
                    "container": "wav", "codec": "pcm_s16le",
                    "sample_rate_hz": 24000, "channels": 1,
                },
                "max_text_chars": current.max_text_chars,
                "recommended_concurrency": 1,
            },
            "runtime": {
                "engine": "genie-tts",
                "engine_version": "2.0.2",
                "device": "cpu",
                "configured_voices": len(current.voices),
                "memory": (
                    runtime.memory_status()
                    if hasattr(runtime, "memory_status") else None
                ),
            },
            "problems": problems,
        }
        return JSONResponse(payload, status_code=200 if ready else 503)

    @app.get("/voices")
    def voices(_: None = Depends(authorize)) -> dict:
        current = current_config()
        return {
            "contract_version": 1,
            "stage": "tts_voice_catalog",
            "voices": [voice.public() for voice in current.voices],
            "default_voice_id": current.default_voice_id,
        }

    @app.post("/voices/import")
    async def import_user_voice(request: Request, _: None = Depends(authorize)) -> dict:
        try:
            payload = await request.json()
            updated, voice = await run_in_threadpool(import_voice, current_config(), payload)
        except VoiceImportError as exc:
            raise ContractError("INVALID_VOICE_BUNDLE", str(exc), 422) from exc
        app.state.config = updated
        if hasattr(runtime, "update_config"):
            runtime.update_config(updated)
        return {
            "contract_version": 1,
            "temporary": True,
            "voice": voice.public(),
            "default_voice_id": updated.default_voice_id,
        }

    @app.post("/job")
    async def job(request: Request, _: None = Depends(authorize)) -> Response:
        try:
            payload = await request.json()
        except Exception as exc:
            raise ContractError("INVALID_REQUEST", "请求体不是有效 JSON") from exc
        current = current_config()
        synthesis = parse_request(payload, current.max_text_chars)
        voice = current.voice(synthesis.voice_id)
        if voice is None:
            raise ContractError("VOICE_NOT_FOUND", f"音色不存在: {synthesis.voice_id}", 404)
        ready, problems = runtime.health()
        if not ready:
            raise ContractError("SERVICE_NOT_READY", "; ".join(problems), 503)
        try:
            audio, duration_ms = runtime.synthesize(voice, synthesis.text)
        except EngineError as exc:
            return JSONResponse(error_body("TTS_FAILED", str(exc), True), status_code=500)
        headers = {
            "X-Genie-TTS-API-Version": "1",
            "X-TTS-Segment-Index": str(synthesis.segment_index),
            "X-TTS-Voice-ID": voice.id,
            "X-Audio-Duration-Ms": str(duration_ms),
            "X-Audio-Sample-Rate-Hz": "24000",
            "X-Audio-Channels": "1",
            "X-Audio-Codec": "pcm_s16le",
        }
        if synthesis.request_id:
            headers["X-Request-ID"] = synthesis.request_id
        return Response(audio, media_type="audio/wav", headers=headers)

    return app


try:
    app = create_app()
except ConfigurationError as exc:
    # Keep uvicorn importable so /health can explain a bad configuration.
    configuration_message = str(exc)
    fallback = FastAPI(title="Genie TTS Engine Plugin", version=__version__)
    fallback.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @fallback.get("/health")
    def invalid_configuration() -> JSONResponse:
        return JSONResponse(
            error_body("SERVICE_NOT_READY", configuration_message, False), status_code=503
        )

    app = fallback
