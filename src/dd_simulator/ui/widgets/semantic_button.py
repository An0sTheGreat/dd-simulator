"""Theme-aware button with a stable semantic role and selected state."""

from PySide6.QtWidgets import QPushButton


class SemanticButton(QPushButton):
    def __init__(
        self,
        text: str,
        *,
        role: str = "secondary",
        object_name: str = "semanticButton",
    ) -> None:
        super().__init__(text)
        self.setObjectName(object_name)
        self.setProperty("buttonRole", role)
        self.setProperty("selected", False)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.setChecked(selected)
        self.style().unpolish(self)
        self.style().polish(self)
