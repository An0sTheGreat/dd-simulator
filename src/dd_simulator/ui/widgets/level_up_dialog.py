"""Theme-aware ability-score choice shown after level advancement."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QSpinBox, QWidget

from dd_simulator.ui.models.presentation import PlayerSummaryView
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_dialog import ThemedDialog


class LevelUpDialog(ThemedDialog):
    allocations_selected = Signal(object)

    def __init__(self, player: PlayerSummaryView, parent: QWidget | None = None) -> None:
        super().__init__("Level Up", parent)
        self.setObjectName("levelUpDialog")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.points = player.pending_ability_points
        self.controls: dict[str, QSpinBox] = {}

        title = QLabel(f"LEVEL {player.level}")
        title.setObjectName("levelUpTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(title)
        self.remaining = QLabel()
        self.remaining.setObjectName("levelUpPointsRemaining")
        self.remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.remaining)
        explanation = QLabel(
            "Spend every ability-score point. A score can receive both points, "
            "but no score can exceed 20."
        )
        explanation.setWordWrap(True)
        self.content_layout.addWidget(explanation)

        grid = QGridLayout()
        grid.addWidget(QLabel("Ability"), 0, 0)
        grid.addWidget(QLabel("Current"), 0, 1)
        grid.addWidget(QLabel("Increase"), 0, 2)
        for row, attribute in enumerate(player.attributes[:6], start=1):
            grid.addWidget(QLabel(attribute.name), row, 0)
            current = QLabel(str(attribute.value))
            current.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(current, row, 1)
            control = QSpinBox()
            control.setRange(0, min(self.points, 20 - attribute.value))
            control.valueChanged.connect(self._refresh)
            grid.addWidget(control, row, 2)
            self.controls[attribute.name] = control
        self.content_layout.addLayout(grid)

        self.confirm = SemanticButton("Apply Level-Up Choices")
        self.confirm.clicked.connect(self._submit)
        self.content_layout.addWidget(self.confirm)
        self._refresh()

    def _refresh(self) -> None:
        spent = sum(control.value() for control in self.controls.values())
        remaining = self.points - spent
        self.remaining.setText(f"Ability-score points remaining: {remaining}")
        self.confirm.setEnabled(remaining == 0)

    def _submit(self) -> None:
        allocations = {
            name: control.value()
            for name, control in self.controls.items()
            if control.value() > 0
        }
        self.allocations_selected.emit(allocations)

