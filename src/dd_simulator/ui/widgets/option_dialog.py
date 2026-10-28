"""Theme-inheriting option chooser for local character generation."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget

from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_dialog import ThemedDialog


class OptionSelectionDialog(ThemedDialog):
    RETRY_RESULT = 2

    def __init__(
        self,
        section_label: str,
        options: tuple[str, str, str],
        parent=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Choose {section_label}", parent)
        self.setObjectName("characterOptionDialog")
        self.setMinimumSize(680, 380)
        layout = self.content_layout
        heading = QLabel(f"Choose a generated {section_label.lower()} option")
        heading.setObjectName("characterOptionDialogTitle")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.option_list = QListWidget()
        self.option_list.setObjectName("characterOptionList")
        self.option_list.setAccessibleName(f"Generated {section_label} options")
        self.option_list.addItems(options)
        self.option_list.setWordWrap(True)
        self.option_list.setCurrentRow(0)
        self.option_list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.option_list, 1)

        buttons = QHBoxLayout()
        cancel = SemanticButton("Cancel", role="secondary")
        cancel.clicked.connect(self.reject)
        retry = SemanticButton("Try Again", role="secondary")
        retry.setObjectName("retryGeneratedOptionsButton")
        retry.clicked.connect(lambda: self.done(self.RETRY_RESULT))
        choose = SemanticButton("Use Selected", role="primary")
        choose.setObjectName("useGeneratedOptionButton")
        choose.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addStretch(1)
        buttons.addWidget(retry)
        buttons.addWidget(choose)
        layout.addLayout(buttons)

    def selected_option(self) -> str | None:
        item = self.option_list.currentItem()
        return None if item is None else item.text()
