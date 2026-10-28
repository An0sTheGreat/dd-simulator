"""Thread-pool adapter for deterministic combat and optional LM narration."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from dd_simulator.lm_studio import LMStudioError
from dd_simulator.state import CombatCommand, GameStateError, GameStateService
from dd_simulator.state.combat import CombatNarrationProvider


LOGGER = logging.getLogger(__name__)


class CombatResolutionSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class CombatResolutionTask(QRunnable):
    def __init__(
        self,
        service: GameStateService,
        *,
        command: CombatCommand | None = None,
        narrator: CombatNarrationProvider | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.command = command
        self.narrator = narrator
        self.signals = CombatResolutionSignals()

    def run(self) -> None:
        try:
            if self.command is None:
                result = self.service.start_combat(narrator=self.narrator)
            else:
                result = self.service.execute_combat_command(
                    self.command, narrator=self.narrator
                )
        except (LMStudioError, GameStateError) as exc:
            self.signals.failed.emit(str(exc))
        except Exception:
            LOGGER.exception("Unexpected combat resolution failure")
            self.signals.failed.emit(
                "Combat could not be resolved because of an unexpected local error."
            )
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
