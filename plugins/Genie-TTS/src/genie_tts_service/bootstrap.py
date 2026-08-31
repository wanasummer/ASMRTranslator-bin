"""Download deterministic base resources without importing Genie interactively."""

from __future__ import annotations

import argparse
import os
import socket
from pathlib import Path


def _proxy_available(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _download_attempts(proxy_port: int) -> list[tuple[str, str, str]]:
    attempts = [("国内 Hugging Face 镜像", "https://hf-mirror.com", "")]
    if _proxy_available(proxy_port):
        attempts.append((
            f"本地代理 127.0.0.1:{proxy_port}",
            "https://huggingface.co",
            f"http://127.0.0.1:{proxy_port}",
        ))
    attempts.append(("Hugging Face 官方直连", "https://huggingface.co", ""))
    return attempts


def _download_snapshot(
    runtime_dir: Path,
    allow_patterns: list[str],
    proxy_port: int,
) -> None:
    from huggingface_hub import snapshot_download

    runtime_dir.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    previous_http = os.environ.get("HTTP_PROXY")
    previous_https = os.environ.get("HTTPS_PROXY")
    try:
        for label, endpoint, proxy in _download_attempts(proxy_port):
            print(f"Trying {label}: {endpoint}", flush=True)
            if proxy:
                os.environ["HTTP_PROXY"] = proxy
                os.environ["HTTPS_PROXY"] = proxy
            else:
                os.environ.pop("HTTP_PROXY", None)
                os.environ.pop("HTTPS_PROXY", None)
            try:
                snapshot_download(
                    repo_id="High-Logic/Genie",
                    repo_type="model",
                    allow_patterns=allow_patterns,
                    local_dir=str(runtime_dir),
                    endpoint=endpoint,
                    max_workers=2,
                )
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                print(f"{label} failed: {exc}", flush=True)
    finally:
        if previous_http is None:
            os.environ.pop("HTTP_PROXY", None)
        else:
            os.environ["HTTP_PROXY"] = previous_http
        if previous_https is None:
            os.environ.pop("HTTPS_PROXY", None)
        else:
            os.environ["HTTPS_PROXY"] = previous_https
    if last_error is not None:
        raise RuntimeError("所有 Genie 资源下载线路均失败") from last_error


def download_base_resources(runtime_dir: Path, proxy_port: int = 7890) -> Path:
    _download_snapshot(runtime_dir, ["GenieData/*"], proxy_port)
    data_dir = runtime_dir / "GenieData"
    if not data_dir.is_dir():
        raise RuntimeError(f"下载完成但未找到 {data_dir}")
    return data_dir


def download_predefined_character(
    runtime_dir: Path,
    character: str,
    proxy_port: int = 7890,
) -> Path:
    aliases = {"feibi", "mika", "thirtyseven"}
    character = character.strip().lower()
    if character not in aliases:
        raise ValueError(f"不支持的预定义角色: {character}")
    relative = Path("CharacterModels") / "v2ProPlus" / character
    pattern = f"{relative.as_posix()}/*"
    _download_snapshot(runtime_dir, [pattern], proxy_port)
    character_dir = runtime_dir / relative
    if not (character_dir / "tts_models").is_dir():
        raise RuntimeError(f"下载完成但未找到角色模型: {character_dir}")
    return character_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--proxy-port", default=7890, type=int)
    parser.add_argument("--character", choices=["feibi", "mika", "thirtyseven"])
    args = parser.parse_args()
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    if args.character:
        print(download_predefined_character(runtime_dir, args.character, args.proxy_port))
    else:
        print(download_base_resources(runtime_dir, args.proxy_port))


if __name__ == "__main__":
    main()
