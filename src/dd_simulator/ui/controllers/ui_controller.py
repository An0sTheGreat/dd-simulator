"""Central semantic action bus for navigation and validated UI requests."""

from PySide6.QtCore import QObject, Signal, Slot


class UiController(QObject):
    navigation_requested = Signal(str)
    tab_changed = Signal(str, int)
    selection_changed = Signal(str, int)
    context_action_requested = Signal(str, int, str)
    action_submitted = Signal(str)
    validation_failed = Signal(str)
    status_message = Signal(str)

    @Slot(str)
    def navigate(self, target: str) -> None:
        normalized = target.strip().lower()
        if normalized:
            self.navigation_requested.emit(normalized)

    @Slot(str, int)
    def change_tab(self, group: str, index: int) -> None:
        self.tab_changed.emit(group, index)

    @Slot(str, int)
    def select_item(self, collection: str, index: int) -> None:
        self.selection_changed.emit(collection, index)
        self.status_message.emit(f"Selected {collection} slot {index + 1}")

    @Slot(str, int, str)
    def request_context_action(self, collection: str, index: int, action: str) -> None:
        self.status_message.emit(
            f"{action.title()} requested for {collection} slot {index + 1}"
        )
        self.context_action_requested.emit(collection, index, action)

    @Slot(str)
    def submit_player_action(self, text: str) -> None:
        normalized = " ".join(text.split())
        if not normalized:
            self.validation_failed.emit("Enter an action before sending.")
            return
        if len(normalized) > 2000:
            self.validation_failed.emit("Actions are limited to 2,000 characters.")
            return
        self.status_message.emit("Player action submitted for resolution")
        self.action_submitted.emit(normalized)
