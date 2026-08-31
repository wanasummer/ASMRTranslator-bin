"""Command-line service entrypoint."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Genie TTS engine plugin")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8003, type=int)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run("genie_tts_service.app:app", host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
