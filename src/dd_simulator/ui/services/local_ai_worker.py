"""Background work for first-run local AI setup."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal

from dd_simulator.local_model import LocalModelClient, LocalModelError
from dd_simulator.local_ai import (
    LOCAL_MODEL_ALIAS,
    LlamaCppRuntime,
    LocalAiConfiguration,
    LocalAiError,
    download_recommended_model,
)


class DownloadSignals(QObject):
    progress = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)
    finished = Signal()


class RecommendedModelDownloadTask(QRunnable):
    def __init__(self, directory: Path, model_key: str) -> None:
        super().__init__()
        self.directory = Path(directory)
        self.model_key = model_key
        self.cancelled = Event()
        self.signals = DownloadSignals()

    def cancel(self) -> None:
        self.cancelled.set()

    def run(self) -> None:
        try:
            path = download_recommended_model(
                self.directory,
                model_key=self.model_key,
                progress=self.signals.progress.emit,
                cancelled=self.cancelled,
            )
            self.signals.succeeded.emit(str(path))
        except (OSError, LocalAiError) as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.finished.emit()


class ActivationSignals(QObject):
    succeeded = Signal(object, str, str)
    failed = Signal(str)
    finished = Signal()


class LocalAiActivationTask(QRunnable):
    def __init__(
        self,
        configuration: LocalAiConfiguration,
        runtime: LlamaCppRuntime,
    ) -> None:
        super().__init__()
        self.configuration = configuration
        self.runtime = runtime
        self.signals = ActivationSignals()

    def run(self) -> None:
        try:
            if self.configuration.mode == "llama_cpp":
                endpoint = self.runtime.start(Path(self.configuration.model_path))
                self.runtime.wait_until_ready()
                model_id = LOCAL_MODEL_ALIAS
            elif self.configuration.mode == "unsloth":
                endpoint = self.configuration.unsloth_base_url
                client = LocalModelClient(
                    endpoint, timeout_seconds=10, api_key=self.configuration.api_key,
                    provider="unsloth",
                )
                model_id = client.discover_models()[0]
            elif self.configuration.mode == "lm_studio":
                endpoint = "http://localhost:1234/v1"
                client = LocalModelClient(endpoint, timeout_seconds=10, provider="lm_studio")
                model_id = client.discover_models()[0]
            else:
                raise LocalAiError("Unsupported local AI setup mode.")
            self.signals.succeeded.emit(self.configuration, endpoint, model_id)
        except (OSError, LocalAiError, LocalModelError) as exc:
            self.runtime.stop()
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.finished.emit()
