"""ASGI entry point: uvicorn app:app --host 0.0.0.0 --port 8000."""

from engine import SUPPORTED_LANGUAGES, load_engine
from service import create_app


app = create_app(load_engine, "parakeet-asr", SUPPORTED_LANGUAGES)
