"""Local llama.cpp configuration, download, and hidden server lifecycle."""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Callable
from urllib.request import Request, urlopen


LOCAL_MODEL_ALIAS = "dnd-simulator-local"
UNSLOTH_DEFAULT_PORT = 8888


@dataclass(frozen=True, slots=True)
class RecommendedModelSpec:
    key: str
    display_name: str
    filename: str
    url: str
    size: int
    sha256: str


QWEN3_4B = RecommendedModelSpec(
    key="qwen3_4b",
    display_name="Qwen3-4B Q4_K_M",
    filename="Qwen3-4B-Q4_K_M.gguf",
    url=(
        "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/"
        "Qwen3-4B-Q4_K_M.gguf?download=true"
    ),
    size=2_497_280_256,
    sha256="7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
)
GEMMA_4_E4B_DISPLAY_NAME = "Gemma 4 E4B Uncensored HauhauCS Aggressive Q8 K P"
RECOMMENDED_MODELS = {QWEN3_4B.key: QWEN3_4B}

# Backward-compatible primary recommendation exports.
RECOMMENDED_MODEL_NAME = QWEN3_4B.filename
RECOMMENDED_MODEL_URL = QWEN3_4B.url
RECOMMENDED_MODEL_SIZE = QWEN3_4B.size
RECOMMENDED_MODEL_SHA256 = QWEN3_4B.sha256


def default_model_directory() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    return Path(root) / "DnDSimulator" / "Models" if root else Path.home() / ".dnd_simulator" / "models"


@dataclass(frozen=True, slots=True)
class LocalAiConfiguration:
    mode: str = ""
    setup_complete: bool = False
    model_directory: str = ""
    model_path: str = ""
    model_id: str = LOCAL_MODEL_ALIAS
    unsloth_port: int = UNSLOTH_DEFAULT_PORT
    api_key: str = field(default="", repr=False)

    @property
    def unsloth_base_url(self) -> str:
        return f"http://127.0.0.1:{self.unsloth_port}/v1"

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "LocalAiConfiguration":
        mode = str(raw.get("mode") or "")
        if mode == "lm_studio":  # Phase 29: the external-server mode moved to Unsloth Studio.
            mode = "unsloth"
        valid_mode = mode in {"llama_cpp", "unsloth"}
        try:
            port = int(raw.get("unsloth_port") or UNSLOTH_DEFAULT_PORT)
        except (TypeError, ValueError):
            port = UNSLOTH_DEFAULT_PORT
        return cls(
            mode=mode if valid_mode else "",
            setup_complete=bool(raw.get("setup_complete")) and valid_mode,
            model_directory=str(raw.get("model_directory") or default_model_directory()),
            model_path=str(raw.get("model_path") or ""),
            model_id=str(raw.get("model_id") or LOCAL_MODEL_ALIAS),
            unsloth_port=port if 0 < port < 65536 else UNSLOTH_DEFAULT_PORT,
            api_key=str(raw.get("api_key") or ""),
        )

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)

    def usable(self) -> bool:
        if not self.setup_complete:
            return False
        if self.mode == "llama_cpp":
            return Path(self.model_path).is_file() and bool(runtime_executables())
        return self.mode == "unsloth" and bool(self.api_key.strip())


class LocalAiError(RuntimeError):
    pass


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "llama_cpp"
    return Path(__file__).resolve().parents[2] / "vendor" / "llama_cpp"


def runtime_executables() -> tuple[Path, ...]:
    root = runtime_root()
    candidates = (root / "vulkan" / "llama-server.exe", root / "cpu" / "llama-server.exe")
    return tuple(path for path in candidates if path.is_file())


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class LlamaCppRuntime:
    def __init__(self, log_directory: Path) -> None:
        self.log_directory = Path(log_directory)
        self.process: subprocess.Popen[bytes] | None = None
        self.port = 0
        self._log_handle: Any = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def server_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, model_path: Path) -> str:
        self.stop()
        if not Path(model_path).is_file():
            raise LocalAiError("The selected GGUF model no longer exists.")
        candidates = runtime_executables()
        if not candidates:
            raise LocalAiError("The packaged llama.cpp runtime is missing.")
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self._log_handle = (self.log_directory / "llama-server.log").open("ab")
        for executable in candidates:
            self.port = _available_port()
            startup = None
            creationflags = 0
            if os.name == "nt":
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW
            self.process = subprocess.Popen(
                [
                    str(executable), "--model", str(model_path), "--alias", LOCAL_MODEL_ALIAS,
                    "--host", "127.0.0.1", "--port", str(self.port), "--ctx-size", "32768",
                    "--jinja", "--n-gpu-layers", "99",
                ],
                stdin=subprocess.DEVNULL,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                startupinfo=startup,
                creationflags=creationflags,
            )
            time.sleep(0.4)
            if self.process.poll() is None:
                return self.base_url
        self.stop()
        raise LocalAiError("llama.cpp could not start. See llama-server.log for details.")

    def wait_until_ready(self, timeout_seconds: float = 300.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.process is None or self.process.poll() is not None:
                raise LocalAiError("llama.cpp stopped while loading the model.")
            try:
                with urlopen(self.server_url + "/health", timeout=2) as response:  # noqa: S310
                    if response.status == 200:
                        return
            except OSError:
                pass
            time.sleep(0.5)
        raise LocalAiError("The local model did not become ready within five minutes.")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None


def download_recommended_model(
    directory: Path,
    *,
    model_key: str = QWEN3_4B.key,
    progress: Callable[[int], None] | None = None,
    cancelled: Event | None = None,
) -> Path:
    model = RECOMMENDED_MODELS.get(model_key)
    if model is None:
        raise LocalAiError("Unknown recommended model selection.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / model.filename
    partial = target.with_suffix(target.suffix + ".part")
    if target.is_file() and _sha256(target) == model.sha256:
        return target
    downloaded = partial.stat().st_size if partial.exists() else 0
    required = max(0, model.size - downloaded)
    if shutil.disk_usage(directory).free < required + 1_073_741_824:
        raise LocalAiError("The selected model folder does not have enough free space.")
    request = Request(model.url, headers={"Range": f"bytes={downloaded}-"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - pinned HTTPS model URL
        append = downloaded > 0 and response.status == 206
        if not append:
            downloaded = 0
        with partial.open("ab" if append else "wb") as output:
            while chunk := response.read(4 * 1024 * 1024):
                if cancelled is not None and cancelled.is_set():
                    raise LocalAiError("Model download cancelled. Partial progress was saved.")
                output.write(chunk)
                downloaded += len(chunk)
                if progress is not None:
                    progress(min(100, int(downloaded * 100 / model.size)))
    if partial.stat().st_size != model.size or _sha256(partial) != model.sha256:
        raise LocalAiError("The downloaded model failed checksum verification.")
    partial.replace(target)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
