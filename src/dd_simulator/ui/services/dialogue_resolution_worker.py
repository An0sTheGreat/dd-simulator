"""Thread-pool adapter for deterministic NPC dialogue and optional LM prose."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from dd_simulator.state import GameStateError, GameStateService
from dd_simulator.state.dialogue import DialogueNarrationProvider


LOGGER = logging.getLogger(__name__)


class DialogueResolutionSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class DialogueResolutionTask(QRunnable):
    def __init__(
        self,
        service: GameStateService,
        npc_id: str,
        response: str,
        narrator: DialogueNarrationProvider | None,
    ) -> None:
        super().__init__()
        self.service = service
        self.npc_id = npc_id
        self.response = response
        self.narrator = narrator
        self.signals = DialogueResolutionSignals()

    def run(self) -> None:
        try:
            result = self.service.resolve_npc_dialogue(
                self.npc_id, self.response, narrator=self.narrator
            )
        except GameStateError as exc:
            self.signals.failed.emit(str(exc))
        except Exception:
            LOGGER.exception("Unexpected NPC dialogue failure")
            self.signals.failed.emit("The conversation could not be resolved due to a local error.")
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
