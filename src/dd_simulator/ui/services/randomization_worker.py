"""Thread-pool adapter for non-blocking character option generation."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from dd_simulator.lm_studio import CharacterRandomizationService, LMStudioError
from dd_simulator.state.character_creation import CharacterCreationDraft


LOGGER = logging.getLogger(__name__)


class RandomizationSignals(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    finished = Signal(str)


class RandomizationTask(QRunnable):
    def __init__(
        self,
        service: CharacterRandomizationService,
        section: str,
        draft: CharacterCreationDraft,
    ) -> None:
        super().__init__()
        self.service = service
        self.section = section
        self.draft = draft
        self.signals = RandomizationSignals()

    def run(self) -> None:
        try:
            options = self.service.generate_options(self.section, self.draft)
        except LMStudioError as exc:
            self.signals.failed.emit(self.section, str(exc))
        except Exception:
            LOGGER.exception("Unexpected character randomization failure")
            self.signals.failed.emit(
                self.section,
                "Character options could not be generated because of an unexpected local error.",
            )
        else:
            self.signals.succeeded.emit(self.section, options)
        finally:
            self.signals.finished.emit(self.section)


class CampaignRandomizationSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class CampaignRandomizationTask(QRunnable):
    def __init__(
        self,
        service: CharacterRandomizationService,
        draft: CharacterCreationDraft,
    ) -> None:
        super().__init__()
        self.service = service
        self.draft = draft
        self.signals = CampaignRandomizationSignals()

    def run(self) -> None:
        try:
            generated = self.service.generate_campaign(self.draft)
        except LMStudioError as exc:
            self.signals.failed.emit(str(exc))
        except Exception:
            LOGGER.exception("Unexpected campaign randomization failure")
            self.signals.failed.emit(
                "The campaign could not be generated because of an unexpected local error."
            )
        else:
            self.signals.succeeded.emit(generated)
        finally:
            self.signals.finished.emit()


class CampaignIntroSignals(QObject):
    succeeded = Signal(str, str)
    failed = Signal(str, str)
    finished = Signal(str)


class CampaignIntroTask(QRunnable):
    """Generate an opening scene after the saved campaign becomes visible."""

    def __init__(
        self,
        service: CharacterRandomizationService,
        campaign_id: str,
        draft: CharacterCreationDraft,
    ) -> None:
        super().__init__()
        self.service = service
        self.campaign_id = campaign_id
        self.draft = draft
        self.signals = CampaignIntroSignals()

    def run(self) -> None:
        try:
            introduction = self.service.generate_intro(self.draft)
        except LMStudioError as exc:
            self.signals.failed.emit(self.campaign_id, str(exc))
        except Exception:
            LOGGER.exception("Unexpected campaign introduction failure")
            self.signals.failed.emit(
                self.campaign_id,
                "The opening scene could not be generated because of an unexpected local error.",
            )
        else:
            self.signals.succeeded.emit(self.campaign_id, introduction)
        finally:
            self.signals.finished.emit(self.campaign_id)
