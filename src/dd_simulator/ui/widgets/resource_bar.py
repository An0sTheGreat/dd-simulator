"""Reusable resource progress bar bound to a presentation model."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QProgressBar

from dd_simulator.ui.models.presentation import ResourceView


class ResourceBar(QProgressBar):
    ANIMATION_DURATION_MS = 300

    def __init__(
        self,
        resource: ResourceView,
        *,
        start_value: int | None = None,
        animate: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("resourceBar")
        self.setTextVisible(True)
        self._animation: QPropertyAnimation | None = None
        self.update_view(resource, start_value=start_value, animate=animate)

    def update_view(
        self,
        resource: ResourceView,
        *,
        start_value: int | None = None,
        animate: bool = False,
    ) -> None:
        """Refresh the displayed resource without changing application state."""

        previous = self.value() if start_value is None else start_value
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        self.setProperty("resourceType", resource.resource_type)
        self.setAccessibleName(resource.name)
        self.setRange(0, max(1, resource.maximum))
        self.setFormat(f"{resource.name}: %v / {resource.maximum}")
        remaining = max(0, resource.maximum - resource.current)
        tooltip = resource.tooltip or f"{remaining} {resource.name.lower()} remaining"
        self.setToolTip(tooltip)
        self.style().unpolish(self)
        self.style().polish(self)
        target = max(self.minimum(), min(resource.current, self.maximum()))
        origin = max(self.minimum(), min(previous, self.maximum()))
        if not animate or origin == target:
            self.setValue(target)
            return
        self.setValue(origin)
        animation = QPropertyAnimation(self, b"value", self)
        animation.setDuration(self.ANIMATION_DURATION_MS)
        animation.setStartValue(origin)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation = animation
        animation.start()
