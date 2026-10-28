"""Thread-pool adapters for local model discovery and evaluation."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from dd_simulator.local_model import LocalModelClient, LocalModelError, ModelEvaluationService


LOGGER = logging.getLogger(__name__)


class ModelTaskSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class ModelDiscoveryTask(QRunnable):
    def __init__(self, client: LocalModelClient) -> None:
        super().__init__()
        self.client = client
        self.signals = ModelTaskSignals()

    def run(self) -> None:
        try:
            result = self.client.discover_model_details()
        except LocalModelError as exc:
            self._emit(self.signals.failed, str(exc))
        except Exception:
            LOGGER.exception("Unexpected local model discovery failure")
            self._emit(self.signals.failed, "Local model discovery failed unexpectedly.")
        else:
            self._emit(self.signals.succeeded, result)
        finally:
            self._emit(self.signals.finished)

    @staticmethod
    def _emit(signal, *values: object) -> None:  # type: ignore[no-untyped-def]
        try:
            signal.emit(*values)
        except RuntimeError:
            # The application may close while localhost discovery is still returning.
            LOGGER.debug("Discarded model-discovery result after UI shutdown")


class ModelEvaluationTask(QRunnable):
    def __init__(self, service: ModelEvaluationService, model_id: str) -> None:
        super().__init__()
        self.service = service
        self.model_id = model_id
        self.signals = ModelTaskSignals()

    def run(self) -> None:
        try:
            result = self.service.evaluate(self.model_id)
        except (LocalModelError, OSError) as exc:
            ModelDiscoveryTask._emit(self.signals.failed, str(exc))
        except Exception:
            LOGGER.exception("Unexpected local model evaluation failure")
            ModelDiscoveryTask._emit(
                self.signals.failed, "Model evaluation failed unexpectedly."
            )
        else:
            ModelDiscoveryTask._emit(self.signals.succeeded, result)
        finally:
            ModelDiscoveryTask._emit(self.signals.finished)


class ModelLoadTask(QRunnable):
    def __init__(self, client: LocalModelClient, model_id: str) -> None:
        super().__init__()
        self.client = client
        self.model_id = model_id
        self.signals = ModelTaskSignals()

    def run(self) -> None:
        try:
            instance_id = self.client.load_exclusive_model(self.model_id)
        except LocalModelError as exc:
            ModelDiscoveryTask._emit(self.signals.failed, str(exc))
        except Exception:
            LOGGER.exception("Unexpected local model model-load failure")
            ModelDiscoveryTask._emit(
                self.signals.failed, "Local model loading failed unexpectedly."
            )
        else:
            ModelDiscoveryTask._emit(self.signals.succeeded, instance_id)
        finally:
            ModelDiscoveryTask._emit(self.signals.finished)
