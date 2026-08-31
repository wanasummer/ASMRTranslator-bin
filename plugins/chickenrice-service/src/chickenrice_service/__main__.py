from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="ChickenRice subtitle HTTP service")
    parser.add_argument("--host", default=os.environ.get("CHICKENRICE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CHICKENRICE_PORT", "7870")))
    parser.add_argument("--runtime-dir", default=os.environ.get("CHICKENRICE_RUNTIME_DIR", "runtime"))
    parser.add_argument("--device", default=os.environ.get("CHICKENRICE_DEVICE", "cuda"))
    parser.add_argument("--compute-type", default=os.environ.get("CHICKENRICE_COMPUTE_TYPE", ""))
    parser.add_argument("--check", action="store_true", help="Validate models and inference runtime, then exit")
    args = parser.parse_args()
    os.environ["CHICKENRICE_RUNTIME_DIR"] = args.runtime_dir
    os.environ["CHICKENRICE_DEVICE"] = args.device
    if args.compute_type:
        os.environ["CHICKENRICE_COMPUTE_TYPE"] = args.compute_type
    if args.check:
        from .config import ServiceConfig

        config = ServiceConfig.from_env()
        problems = config.validate()
        print(json.dumps({
            "status": "ready" if not problems else "not_ready",
            "device": config.device,
            "runtime": config.runtime_status(),
            "capabilities": config.capability_status(),
            "problems": problems,
        }, ensure_ascii=False, indent=2))
        if problems:
            raise SystemExit(1)
        return
    import uvicorn

    uvicorn.run("chickenrice_service.app:create_app", factory=True, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
