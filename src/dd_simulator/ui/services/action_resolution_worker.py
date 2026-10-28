"""Cancelable thread-pool adapter for non-combat action resolution."""

from __future__ import annotations

import logging
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal

from dd_simulator.local_model import LocalModelError
from dd_simulator.state import ActionCancelledError, GameStateError, GameStateService
from dd_simulator.state.turns import ActionOutcomeProvider


LOGGER = logging.getLogger(__name__)


class ActionResolutionSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()


class ActionResolutionTask(QRunnable):
    def __init__(
        self,
        service: GameStateService,
        provider: ActionOutcomeProvider,
        action: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.provider = provider
        self.action = action
        self.signals = ActionResolutionSignals()
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            result = self.service.resolve_player_action(
                self.action,
                self.provider,
                cancelled=self._cancelled.is_set,
            )
        except ActionCancelledError:
            self.signals.cancelled.emit()
        except (LocalModelError, GameStateError) as exc:
            self.signals.failed.emit(str(exc))
        except Exception:
            LOGGER.exception("Unexpected player-action resolution failure")
            self.signals.failed.emit(
                "The action could not be resolved because of an unexpected local error."
            )
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
