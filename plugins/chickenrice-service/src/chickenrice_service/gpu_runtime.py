"""GPU runtime discovery, process configuration, and health diagnostics."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import site
import sys
from functools import lru_cache
from pathlib import Path


GPU_DEVICES = frozenset({"cuda", "amd", "rocm", "hip"})
WINDOWS_DLLS = (
    "cublas64_12.dll",
    "cublasLt64_12.dll",
    "cudnn64_9.dll",
    "cudnn_ops64_9.dll",
)
LINUX_LIBRARIES = ("libcublas.so.12", "libcudnn.so.9")
_DLL_HANDLES: list[object] = []
_REGISTERED_DLL_DIRS: set[str] = set()


def _candidate_runtime_dirs() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("CHICKENRICE_GPU_RUNTIME_DIR", "").strip()
    if override:
        candidates.append(Path(override))
    cuda_path = os.environ.get("CUDA_PATH", "").strip()
    if cuda_path:
        candidates.append(Path(cuda_path) / "bin")
    roots = {Path(sys.prefix) / "Lib" / "site-packages"}
    try:
        roots.update(Path(value) for value in site.getsitepackages())
    except AttributeError:
        pass
    for root in roots:
        candidates.extend((root / "nvidia" / "cublas" / "bin", root / "nvidia" / "cudnn" / "bin"))
    candidates.extend(Path(value) for value in os.environ.get("PATH", "").split(os.pathsep) if value)
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate.resolve()) if candidate.exists() else str(candidate)
        key = normalized.casefold()
        if key not in seen and candidate.is_dir():
            seen.add(key)
            result.append(Path(normalized))
    return result


def configure_gpu_runtime(device: str) -> list[Path]:
    """Expose bundled NVIDIA DLL directories to this process and child runners."""
    if device.lower() not in GPU_DEVICES:
        return []
    directories = _candidate_runtime_dirs()
    if not directories:
        return []
    current = os.environ.get("PATH", "")
    existing = {value.casefold() for value in current.split(os.pathsep) if value}
    additions = [str(path) for path in directories if str(path).casefold() not in existing]
    if additions:
        os.environ["PATH"] = os.pathsep.join(additions + ([current] if current else []))
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for directory in directories:
            key = str(directory).casefold()
            if key not in _REGISTERED_DLL_DIRS:
                try:
                    _DLL_HANDLES.append(os.add_dll_directory(str(directory)))
                    _REGISTERED_DLL_DIRS.add(key)
                except OSError:
                    continue
    return directories


def _find_windows_dll(name: str, directories: list[Path]) -> Path | None:
    for directory in directories:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    located = shutil.which(name)
    return Path(located) if located else None


@lru_cache(maxsize=8)
def inspect_gpu_runtime(device: str) -> dict:
    """Return a stable health payload for the configured inference device."""
    normalized = device.lower()
    if normalized not in GPU_DEVICES:
        return {"available": True, "device": normalized, "provider": "cpu", "problems": []}
    directories = configure_gpu_runtime(normalized)
    problems: list[str] = []
    system = platform.system()
    if system == "Windows":
        missing = [name for name in WINDOWS_DLLS if _find_windows_dll(name, directories) is None]
        if missing:
            problems.append("缺少 CUDA 12/cuDNN 9 运行库: " + ", ".join(missing))
        else:
            for name in WINDOWS_DLLS:
                try:
                    getattr(ctypes, "WinDLL", ctypes.CDLL)(name)
                except OSError as exc:
                    problems.append(f"GPU 运行库无法加载 {name}: {exc}")
                    break
        try:
            getattr(ctypes, "WinDLL", ctypes.CDLL)("nvcuda.dll")
        except OSError:
            problems.append("NVIDIA 驱动不可用（nvcuda.dll 无法加载）")
    elif system == "Linux":
        for name in LINUX_LIBRARIES:
            try:
                ctypes.CDLL(name)
            except OSError as exc:
                problems.append(f"GPU 运行库无法加载 {name}: {exc}")
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() < 1:
            problems.append("CTranslate2 未检测到可用 NVIDIA GPU")
    except Exception as exc:  # import and driver errors are both actionable here
        problems.append(f"CTranslate2 GPU 自检失败: {exc}")
    return {
        "available": not problems,
        "device": normalized,
        "provider": "ctranslate2-cuda",
        "library_dirs": [str(path) for path in directories],
        "problems": problems,
    }
