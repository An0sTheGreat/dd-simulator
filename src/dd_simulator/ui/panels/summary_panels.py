"""Data-driven player and location summaries with state-matched visuals."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from dd_simulator.ui.models.presentation import (
    LocationSummaryView,
    PlayerSummaryView,
    ResourceView,
    VisualAssetView,
)
from dd_simulator.ui.location_images import resolve_location_image
from dd_simulator.ui.panels.common import DashboardPanel, semantic_label
from dd_simulator.ui.widgets.resource_bar import ResourceBar


def _resource_widget(
    resource: ResourceView,
    *,
    start_value: int | None = None,
    animate: bool = False,
) -> tuple[QWidget, ResourceBar]:
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    bar = ResourceBar(resource, start_value=start_value, animate=animate)
    row.addWidget(bar, 1)
    return host, bar


def _consolidated_resources(
    data: PlayerSummaryView,
    resources: tuple[ResourceView, ...] | None,
) -> tuple[ResourceView, ...]:
    seen_types: set[str] = set()
    consolidated: list[ResourceView] = []
    for resource in (resources or data.resources):
        if resource.resource_type == "experience":
            continue
        if resource.resource_type not in seen_types:
            seen_types.add(resource.resource_type)
            consolidated.append(resource)
    consolidated.append(data.experience)
    return tuple(consolidated)


def _apply_visual(
    label: QLabel,
    visual: VisualAssetView | None,
    *,
    fallback_text: str,
    target_size: QSize,
) -> None:
    """Load confirmed registry art or present an explicit safe placeholder state."""

    label.setProperty("visualState", "unregistered")
    label.setText(fallback_text)
    if visual is None:
        label.setToolTip("No confirmed visual is registered for this state.")
        return
    label.setProperty("visualState", visual.status)
    detail = f"Visual Registry version {visual.version} — {visual.status.title()}"
    if visual.prompt_summary:
        detail += f"\n{visual.prompt_summary}"
    label.setToolTip(detail)
    if visual.status == "pending":
        label.setText("VISUAL PENDING\nCONFIRMATION")
        return
    if visual.status == "missing" or not visual.path:
        label.setText("VISUAL FILE\nMISSING")
        return
    path = Path(visual.path)
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        label.setProperty("visualState", "missing")
        label.setText("VISUAL FILE\nUNREADABLE")
        return
    label.setText("")
    source_setter = getattr(label, "set_source_pixmap", None)
    if callable(source_setter):
        source_setter(pixmap)
    else:
        label.setPixmap(
            pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


def _apply_location_catalog_visual(label: QLabel, data: LocationSummaryView) -> None:
    path = resolve_location_image(
        name=data.name,
        biome=data.biome,
        time_label=data.time_label,
        weather=data.weather,
        danger=data.danger,
    )
    if path is None:
        return
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return
    label.setProperty("visualState", "catalog")
    label.setToolTip(f"Packaged {data.biome or 'location'} scene: {path.stem}")
    label.setText("")
    source_setter = getattr(label, "set_source_pixmap", None)
    if callable(source_setter):
        source_setter(pixmap)
    else:
        label.setPixmap(
            pixmap.scaled(
                QSize(320, 180),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class PlayerSummaryPanel(DashboardPanel):
    def __init__(
        self,
        data: PlayerSummaryView,
        *,
        resources: tuple[ResourceView, ...] | None = None,
        initial_resource_values: dict[str, int] | None = None,
        animate_resources: bool = False,
    ) -> None:
        super().__init__("playerSummaryPanel", "PLAYER SUMMARY & RESOURCES")

        body = QHBoxLayout()
        body.setSpacing(12)
        portrait = QLabel(data.portrait_initials)
        portrait.setObjectName("portraitPlaceholder")
        portrait.setAccessibleName(f"Portrait placeholder for {data.name}")
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait.setFixedSize(88, 88)
        _apply_visual(
            portrait,
            data.visual,
            fallback_text=data.portrait_initials,
            target_size=QSize(84, 84),
        )
        portrait.setAccessibleName(
            f"{'Confirmed portrait' if data.visual and data.visual.status == 'confirmed' else 'Portrait placeholder'} for {data.name}"
        )
        body.addWidget(portrait)

        details = QVBoxLayout()
        details.setSpacing(4)
        name = semantic_label(data.name, object_name="playerName", text_role="heading")
        subtitle = semantic_label(
            f"Level {data.level} {data.character_class}", text_role="secondary"
        )
        details.addWidget(name)
        details.addWidget(subtitle)

        resource_grid = QGridLayout()
        resource_grid.setObjectName("playerResourceGrid")
        resource_grid.setContentsMargins(0, 0, 0, 0)
        resource_grid.setHorizontalSpacing(5)
        resource_grid.setVerticalSpacing(3)
        consolidated = _consolidated_resources(data, resources)
        self.resource_bars: dict[str, ResourceBar] = {}
        for index, resource in enumerate(consolidated[:-1]):
            host, bar = _resource_widget(
                resource,
                start_value=(initial_resource_values or {}).get(resource.resource_type),
                animate=animate_resources,
            )
            resource_grid.addWidget(host, index // 2, index % 2)
            self.resource_bars[resource.resource_type] = bar
        experience_row = (max(0, len(consolidated) - 1) + 1) // 2
        experience = consolidated[-1]
        experience_host, experience_bar = _resource_widget(
            experience,
            start_value=(initial_resource_values or {}).get(experience.resource_type),
            animate=animate_resources,
        )
        resource_grid.addWidget(experience_host, experience_row, 0, 1, 2)
        self.resource_bars[experience.resource_type] = experience_bar
        details.addLayout(resource_grid)

        metadata = QHBoxLayout()
        self.currency_label = semantic_label(
            f"Gold: {data.currency:,}", text_role="accent"
        )
        metadata.addWidget(self.currency_label)
        metadata.addStretch(1)
        self.carry_label = semantic_label(
            f"Carry: {data.carry_weight} / {data.carry_capacity}",
            text_role="secondary",
        )
        metadata.addWidget(self.carry_label)
        details.addLayout(metadata)
        body.addLayout(details, 1)
        self.content_layout.addLayout(body, 1)

    def update_view(
        self,
        data: PlayerSummaryView,
        *,
        resources: tuple[ResourceView, ...] | None = None,
        animate_resources: bool = True,
    ) -> None:
        """Refresh values that can change during an in-place dashboard update."""

        for resource in _consolidated_resources(data, resources):
            bar = self.resource_bars.get(resource.resource_type)
            if bar is not None:
                bar.update_view(resource, animate=animate_resources)
        self.currency_label.setText(f"Gold: {data.currency:,}")
        self.carry_label.setText(
            f"Carry: {data.carry_weight} / {data.carry_capacity}"
        )


class LocationSummaryPanel(DashboardPanel):
    def __init__(self, data: LocationSummaryView) -> None:
        super().__init__("locationSummaryPanel", "LOCATION SUMMARY")

        details = QGridLayout()
        details.setHorizontalSpacing(12)
        details.setVerticalSpacing(6)

        rows = (
            ("Location", data.name, "accent"),
            ("Region", data.region, "body"),
            ("Time", data.time_label, "body"),
            ("Weather", data.weather, "body"),
            ("Danger", data.danger, "success"),
            ("Route", data.route_status, "secondary"),
        )
        for row, (label, value, role) in enumerate(rows):
            details.addWidget(semantic_label(label, text_role="muted"), row, 0)
            details.addWidget(
                semantic_label(value, object_name="locationValue", text_role=role),
                row,
                1,
            )
        details.setColumnStretch(1, 1)
        self.content_layout.addLayout(details, 1)
