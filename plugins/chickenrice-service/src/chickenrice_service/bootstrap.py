"""Install the pinned upstream source and model without requiring Git.

Network selection is deliberately China-friendly: an existing proxy is validated
first; otherwise domestic mirrors are selected for GitHub, Hugging Face and PyPI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import gc
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


UPSTREAM_TAG = "v1.10"
UPSTREAM_ARCHIVE = (
    "https://github.com/TransWithAI/Faster-Whisper-TransWithAI-ChickenRice/"
    f"archive/refs/tags/{UPSTREAM_TAG}.zip"
)
JA_MODEL_REPO = "TransWithAI/whisper-ja-1.5B-ct2"
ZH_MODEL_REPO = "chickenrice0721/whisper-large-v2-translate-zh-v0.2-st-ct2"
VAD_REPO = "TransWithAI/Whisper-Vad-EncDec-ASMR-onnx"
COMMON_PROXY_PORTS = (7890, 7897, 10809, 10808, 20171, 2080)
PROXY_ENV_NAMES = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
    "PIP_PROXY", "pip_proxy",
)


@dataclass(frozen=True)
class NetworkPolicy:
    proxy: str | None
    github_prefix: str
    hf_endpoint: str
    pip_index: str

    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        # A stale ``pip.ini`` proxy otherwise leaks into PEP 517 build
        # subprocesses even after HTTP(S)_PROXY has been cleared.  All indexes
        # and proxies used by this installer are supplied explicitly.
        env["PIP_CONFIG_FILE"] = os.devnull
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env.pop("PIP_PROXY", None)
        env.pop("pip_proxy", None)
        if self.proxy:
            env.pop("NO_PROXY", None)
            env.pop("no_proxy", None)
            env["HTTP_PROXY"] = self.proxy
            env["HTTPS_PROXY"] = self.proxy
            env["http_proxy"] = self.proxy
            env["https_proxy"] = self.proxy
        else:
            for name in PROXY_ENV_NAMES:
                env.pop(name, None)
            # requests/pip can fall back to the Windows Internet Settings proxy
            # when proxy environment variables are absent.  ``*`` explicitly
            # bypasses that stale system proxy for every domestic mirror host.
            env["NO_PROXY"] = "*"
            env["no_proxy"] = "*"
            env["HF_ENDPOINT"] = self.hf_endpoint
            env["PIP_INDEX_URL"] = self.pip_index
        return env


def _port_open(port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _proxy_works(proxy: str, timeout: float = 3.0) -> bool:
    if not proxy.lower().startswith(("http://", "https://")):
        return False
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    opener = urllib.request.build_opener(handler)
    request = urllib.request.Request(
        "https://github.com/favicon.ico",
        headers={"User-Agent": "ChickenRice-Service/0.1", "Range": "bytes=0-0"},
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            response.read(1)
        return True
    except Exception:
        return False


def detect_network_policy() -> NetworkPolicy:
    override = os.environ.get("CHICKENRICE_PROXY", "").strip()
    candidates = [override] if override else []
    for name in (
        "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy",
        "PIP_PROXY", "pip_proxy",
    ):
        value = os.environ.get(name, "").strip()
        if value and value not in candidates:
            candidates.append(value)
    for port in COMMON_PROXY_PORTS:
        if _port_open(port):
            candidates.append(f"http://127.0.0.1:{port}")
    for candidate in candidates:
        if _proxy_works(candidate):
            print(f"[network] 使用已验证代理: {candidate}")
            return NetworkPolicy(candidate, "", "https://huggingface.co", "https://pypi.org/simple")
    github_prefix = os.environ.get("CHICKENRICE_GITHUB_MIRROR", "https://ghfast.top/").strip()
    hf_endpoint = os.environ.get("CHICKENRICE_HF_ENDPOINT", "https://hf-mirror.com").strip().rstrip("/")
    pip_index = os.environ.get(
        "CHICKENRICE_PIP_INDEX", "https://pypi.tuna.tsinghua.edu.cn/simple"
    ).strip()
    print(f"[network] 未发现可用本地代理，使用国内镜像: HF={hf_endpoint}, PyPI={pip_index}")
    return NetworkPolicy(None, github_prefix, hf_endpoint, pip_index)


def _opener(policy: NetworkPolicy):
    if policy.proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": policy.proxy, "https": policy.proxy})
        )
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


@contextmanager
def applied_network_environment(policy: NetworkPolicy):
    """Apply one policy to in-process HTTP clients, then restore the caller."""
    env = policy.environment()
    names = set(PROXY_ENV_NAMES) | {
        "HF_ENDPOINT",
        "NO_PROXY",
        "no_proxy",
        "PIP_CONFIG_FILE",
        "PIP_DISABLE_PIP_VERSION_CHECK",
    }
    old_env = {name: os.environ.get(name) for name in names}
    for name in names:
        if name in env:
            os.environ[name] = env[name]
        else:
            os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old_value


def download(urls: list[str], destination: Path, policy: NetworkPolicy) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    opener = _opener(policy)
    last_error: Exception | None = None
    for url in urls:
        try:
            print(f"[download] {url}")
            request = urllib.request.Request(url, headers={"User-Agent": "ChickenRice-Service/0.1"})
            with opener.open(request, timeout=60) as response, destination.open("wb") as target:
                shutil.copyfileobj(response, target, length=1024 * 1024)
            if destination.stat().st_size == 0:
                raise RuntimeError("下载结果为空")
            return
        except Exception as exc:
            last_error = exc
            destination.unlink(missing_ok=True)
            print(f"[download] 失败，尝试下一个地址: {exc}")
    raise RuntimeError(f"所有下载地址均失败: {last_error}")


def _safe_extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError(f"压缩包包含不安全路径: {member.filename}")
        bundle.extractall(destination)
    directories = [path for path in destination.iterdir() if path.is_dir()]
    if len(directories) != 1:
        raise RuntimeError("无法识别海南鸡源码压缩包根目录")
    return directories[0]


def install_dependencies(
    plugin_root: Path,
    device: str,
    policy: NetworkPolicy,
) -> None:
    extra = "engine-gpu" if device.lower() in {"cuda", "amd", "rocm", "hip"} else "engine"
    command = [
        sys.executable,
        "-m",
        "pip",
        "--isolated",
        "install",
        "--upgrade",
        "--index-url",
        policy.pip_index,
    ]
    if sys.platform == "win32" and extra == "engine-gpu":
        # Some regional mirrors do not synchronize NVIDIA's large Windows wheels.
        # Keep the selected mirror first and use official PyPI as a deterministic fallback.
        command.extend(["--extra-index-url", "https://pypi.org/simple"])
    command.extend(["-e", f"{plugin_root}[{extra}]"])
    subprocess.run(command, env=policy.environment(), check=True)


def verify_inference_runtime(
    runtime_dir: Path,
    device: str,
    model_factory=None,
) -> dict:
    """Fail installation unless the selected backend can load a real Whisper model."""
    from .gpu_runtime import inspect_gpu_runtime

    inspect_gpu_runtime.cache_clear()
    status = inspect_gpu_runtime(device)
    if not status["available"]:
        raise RuntimeError("GPU 运行环境不可用：" + "；".join(status["problems"]))
    if model_factory is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("缺少 faster-whisper 推理依赖") from exc
        model_factory = WhisperModel
    model_dir = runtime_dir / "models" / "japanese-asr"
    compute_type = "int8_float16" if device.lower() in {"cuda", "amd", "rocm", "hip"} else "int8"
    backend_device = "cuda" if device.lower() in {"amd", "rocm", "hip"} else device.lower()
    try:
        model = model_factory(str(model_dir), device=backend_device, compute_type=compute_type)
    except Exception as exc:
        raise RuntimeError(f"推理模型启动自检失败：{exc}") from exc
    del model
    gc.collect()
    return status


def install_upstream(runtime_dir: Path, policy: NetworkPolicy, force: bool) -> Path:
    destination = runtime_dir / "upstream"
    if (destination / "infer.py").is_file() and not force:
        print(f"[bootstrap] 海南鸡源码运行时已存在: {destination}")
        return destination
    with tempfile.TemporaryDirectory(prefix="chickenrice-source-") as temp_text:
        temp = Path(temp_text)
        archive = temp / "upstream.zip"
        urls = [UPSTREAM_ARCHIVE]
        if not policy.proxy and policy.github_prefix:
            urls.insert(0, policy.github_prefix + UPSTREAM_ARCHIVE)
        download(urls, archive, policy)
        extracted = _safe_extract(archive, temp / "source")
        staging = runtime_dir / "upstream.staging"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(extracted, staging)
        if destination.exists():
            shutil.rmtree(destination)
        staging.replace(destination)
    shutil.copy2(destination / "generation_config.json5", runtime_dir / "generation_config.json5")
    (runtime_dir / "UPSTREAM_VERSION").write_text(UPSTREAM_TAG + "\n", encoding="utf-8")
    return destination


def _download_model(repo: str, target: Path, endpoint: str, force: bool, snapshot_download) -> None:
    if force and target.exists():
        shutil.rmtree(target)
    snapshot_download(
        repo_id=repo,
        local_dir=target,
        endpoint=endpoint,
        allow_patterns=["*.json", "*.bin", "*.txt", "*.model"],
    )
    if not (target / "model.bin").is_file():
        raise RuntimeError(f"模型安装不完整: {target / 'model.bin'}")


def install_models(
    runtime_dir: Path,
    policy: NetworkPolicy,
    force: bool,
    *,
    with_vad: bool = True,
    with_zh: bool = True,
) -> Path:
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError as exc:
        raise RuntimeError("缺少 huggingface-hub，请不要使用 --skip-dependencies") from exc
    models = runtime_dir / "models"
    japanese_model_dir = models / "japanese-asr"
    chinese_model_dir = models / "chinese-translate"
    endpoint = policy.hf_endpoint
    with applied_network_environment(policy):
        _download_model(JA_MODEL_REPO, japanese_model_dir, endpoint, force, snapshot_download)
        if with_zh:
            _download_model(ZH_MODEL_REPO, chinese_model_dir, endpoint, force, snapshot_download)
        if with_vad:
            models.mkdir(parents=True, exist_ok=True)
            vad_model = hf_hub_download(VAD_REPO, "model.onnx", endpoint=endpoint)
            vad_meta = hf_hub_download(VAD_REPO, "model_metadata.json", endpoint=endpoint)
            shutil.copy2(vad_model, models / "whisper_vad.onnx")
            shutil.copy2(vad_meta, models / "whisper_vad_metadata.json")
            whisper_base = models / "whisper-base"
            whisper_base.mkdir(parents=True, exist_ok=True)
            for filename in ("preprocessor_config.json", "config.json", "tokenizer.json", "vocab.json"):
                source = hf_hub_download("openai/whisper-base", filename, endpoint=endpoint)
                shutil.copy2(source, whisper_base / filename)
    vad_path = models / "whisper_vad.onnx"
    digest = hashlib.sha256(vad_path.read_bytes()).hexdigest() if vad_path.is_file() else None
    installation = {
        "upstream": UPSTREAM_TAG if with_vad else None,
        "japanese_asr_model": JA_MODEL_REPO,
        "chinese_translation_model": ZH_MODEL_REPO if with_zh else None,
        "vad_sha256": digest,
        "capabilities": {
            "japanese_asr": True,
            "chinese_translation": with_zh,
            "chickenrice_vad": with_vad,
        },
    }
    (runtime_dir / "INSTALLATION.json").write_text(
        json.dumps(installation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return japanese_model_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="安装 ChickenRice 服务运行时")
    parser.add_argument("--runtime-dir", default="runtime")
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu", "amd"))
    parser.add_argument("--skip-dependencies", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    runtime = Path(args.runtime_dir).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    plugin_root = Path(__file__).resolve().parents[2]
    policy = detect_network_policy()
    if not args.skip_dependencies:
        install_dependencies(plugin_root, args.device, policy)
    install_upstream(runtime, policy, args.force)
    install_models(
        runtime,
        policy,
        args.force,
        with_vad=True,
        with_zh=True,
    )
    status = verify_inference_runtime(runtime, args.device)
    installation_path = runtime / "INSTALLATION.json"
    installation = json.loads(installation_path.read_text(encoding="utf-8"))
    installation["runtime"] = {
        "device": args.device,
        "verified": True,
        "provider": status["provider"],
    }
    installation_path.write_text(
        json.dumps(installation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("[bootstrap] 安装完成")
    print(f"[bootstrap] 启动命令: chickenrice-service --runtime-dir \"{runtime}\" --device {args.device}")


if __name__ == "__main__":
    main()
