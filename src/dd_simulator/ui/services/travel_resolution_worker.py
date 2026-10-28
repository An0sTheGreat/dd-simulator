"""Thread-pool adapter for deterministic travel and optional LM prose."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from dd_simulator.lm_studio import LMStudioError
from dd_simulator.state import GameStateError, GameStateService
from dd_simulator.state.travel import TravelNarrationProvider


LOGGER = logging.getLogger(__name__)


class TravelResolutionSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class TravelResolutionTask(QRunnable):
    def __init__(
        self,
        service: GameStateService,
        *,
        route_id: str | None = None,
        camp_duration: int | None = None,
        narrator: TravelNarrationProvider | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.route_id = route_id
        self.camp_duration = camp_duration
        self.narrator = narrator
        self.signals = TravelResolutionSignals()

    def run(self) -> None:
        try:
            if self.route_id is not None:
                result = self.service.travel_to(
                    self.route_id, narrator=self.narrator
                )
            elif self.camp_duration is not None:
                result = self.service.make_camp(
                    duration_minutes=self.camp_duration,
                    narrator=self.narrator,
                )
            else:
                raise GameStateError("Travel task did not receive an action.")
        except (LMStudioError, GameStateError) as exc:
            self.signals.failed.emit(str(exc))
        except Exception:
            LOGGER.exception("Unexpected travel resolution failure")
            self.signals.failed.emit(
                "Travel could not be resolved because of an unexpected local error."
            )
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
