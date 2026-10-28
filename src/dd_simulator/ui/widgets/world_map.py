"""Interactive, theme-driven world map and travel confirmation widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import (
    MapLocationView,
    TravelRouteView,
    WorldMapView,
)
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_dialog import ThemedDialog


class WorldMapPanel(QFrame):
    travel_requested = Signal(str)
    camp_requested = Signal(int)

    def __init__(self, world_map: WorldMapView | None) -> None:
        super().__init__()
        self.setObjectName("worldMapPanel")
        self.world_map = world_map
        self.selected_route: TravelRouteView | None = None
        self.location_buttons: dict[str, SemanticButton] = {}
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        canvas_frame = QFrame()
        canvas_frame.setObjectName("worldMapCanvas")
        canvas_layout = QVBoxLayout(canvas_frame)
        compass = QLabel("NORTH")
        compass.setObjectName("mapCompass")
        compass.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_layout.addWidget(compass)
        scroll = QScrollArea()
        scroll.setObjectName("worldMapScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        map_content = QWidget()
        map_content.setObjectName("worldMapContent")
        self.map_grid = QGridLayout(map_content)
        self.map_grid.setContentsMargins(12, 12, 12, 12)
        self.map_grid.setHorizontalSpacing(18)
        self.map_grid.setVerticalSpacing(18)
        for column in range(6):
            self.map_grid.setColumnStretch(column, 1)
        for row in range(4):
            self.map_grid.setRowStretch(row, 1)
        scroll.setWidget(map_content)
        canvas_layout.addWidget(scroll, 1)
        root.addWidget(canvas_frame, 7)

        details = QFrame()
        details.setObjectName("travelDetailsPanel")
        details.setMinimumWidth(330)
        detail_layout = QVBoxLayout(details)
        title = QLabel("TRAVEL ROUTE")
        title.setObjectName("travelDetailsTitle")
        detail_layout.addWidget(title)
        self.destination_label = QLabel("Select a discovered location.")
        self.destination_label.setObjectName("travelDestinationName")
        self.destination_label.setWordWrap(True)
        detail_layout.addWidget(self.destination_label)
        self.route_description = QLabel(
            "Reachable destinations are connected to the current location by a known route."
        )
        self.route_description.setObjectName("travelRouteDescription")
        self.route_description.setWordWrap(True)
        detail_layout.addWidget(self.route_description)
        self.route_stats = QLabel("")
        self.route_stats.setObjectName("travelRouteStats")
        self.route_stats.setWordWrap(True)
        detail_layout.addWidget(self.route_stats)
        self.route_requirement = QLabel("")
        self.route_requirement.setObjectName("travelRouteRequirement")
        self.route_requirement.setWordWrap(True)
        detail_layout.addWidget(self.route_requirement)
        self.travel_button = SemanticButton(
            "Select a Destination", role="primary", object_name="confirmMapTravelButton"
        )
        self.travel_button.setEnabled(False)
        self.travel_button.clicked.connect(self._emit_travel)
        detail_layout.addWidget(self.travel_button)
        detail_layout.addStretch(1)
        camp_title = QLabel("CAMP")
        camp_title.setObjectName("travelDetailsTitle")
        detail_layout.addWidget(camp_title)
        camp_help = QLabel(
            "Camping advances time and recovers resources. Eight hours also resets limited uses."
        )
        camp_help.setObjectName("travelRouteDescription")
        camp_help.setWordWrap(True)
        detail_layout.addWidget(camp_help)
        camp_row = QHBoxLayout()
        for label, duration in (("Camp 4 Hours", 240), ("Camp 8 Hours", 480)):
            button = SemanticButton(label, role="secondary", object_name="mapCampButton")
            button.setEnabled(bool(world_map and world_map.can_camp))
            button.clicked.connect(
                lambda _checked=False, minutes=duration: self.camp_requested.emit(minutes)
            )
            camp_row.addWidget(button)
        detail_layout.addLayout(camp_row)
        if world_map and world_map.last_journey:
            last = QLabel(f"Last journey: {world_map.last_journey}")
            last.setObjectName("lastJourneyLabel")
            last.setWordWrap(True)
            detail_layout.addWidget(last)
        root.addWidget(details, 3)

        if world_map is None or not world_map.locations:
            unavailable = QLabel("No discovered map locations are available.")
            unavailable.setObjectName("mapEmptyState")
            unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.map_grid.addWidget(unavailable, 0, 0, 4, 6)
        else:
            self._populate_locations(world_map.locations)

    def _populate_locations(self, locations: tuple[MapLocationView, ...]) -> None:
        for location in locations:
            label = f"{location.name}\n{location.region}"
            if location.current:
                label += "\nCURRENT LOCATION"
            elif not location.visited:
                label += "\nDISCOVERED"
            button = SemanticButton(label, role="secondary", object_name="mapLocationNode")
            button.setProperty("current", location.current)
            button.setProperty("visited", location.visited)
            button.setProperty("biome", location.biome)
            button.setAccessibleName(
                f"{location.name}, {'current location' if location.current else 'map location'}"
            )
            button.setToolTip(f"{location.description}\nDanger: {location.danger}")
            button.clicked.connect(
                lambda _checked=False, location_id=location.id: self.select_location(location_id)
            )
            self.location_buttons[location.id] = button
            row = max(0, min(3, location.map_y))
            column = max(0, min(5, location.map_x))
            self.map_grid.addWidget(button, row, column)

    def select_location(self, location_id: str) -> None:
        if self.world_map is None:
            return
        location = next(
            (value for value in self.world_map.locations if value.id == location_id), None
        )
        if location is None:
            return
        for button_id, button in self.location_buttons.items():
            button.setProperty("selected", button_id == location_id)
            button.style().unpolish(button)
            button.style().polish(button)
        routes = [
            route
            for route in self.world_map.routes
            if route.target_location_id == location_id
        ]
        self.selected_route = routes[0] if routes else None
        self.destination_label.setText(location.name)
        if location.current:
            self.route_description.setText(location.description)
            self.route_stats.setText("You are currently here.")
            self.route_requirement.setText("")
            self.travel_button.setText("Current Location")
            self.travel_button.setEnabled(False)
            return
        if self.selected_route is None:
            self.route_description.setText(location.description)
            self.route_stats.setText("No direct known route from the current location.")
            self.route_requirement.setText("")
            self.travel_button.setText("Route Unavailable")
            self.travel_button.setEnabled(False)
            return
        route = self.selected_route
        hours, minutes = divmod(route.travel_minutes, 60)
        duration = f"{hours}h {minutes}m" if minutes else f"{hours}h"
        self.route_description.setText(route.description or location.description)
        self.route_stats.setText(
            f"Distance: {route.distance_miles} miles\n"
            f"Travel time: {duration}\n"
            f"Stamina cost: {route.stamina_cost}\n"
            f"Danger: {route.danger_rating} / 10\n"
            f"Route status: {route.status.title()}"
        )
        self.route_requirement.setText(route.requirement)
        self.travel_button.setText(
            f"Travel to {location.name}" if route.reachable else "Route Unavailable"
        )
        self.travel_button.setEnabled(route.reachable)

    def _emit_travel(self) -> None:
        if self.selected_route is not None and self.selected_route.reachable:
            self.travel_requested.emit(self.selected_route.id)


class TravelConfirmationDialog(ThemedDialog):
    def __init__(self, route: TravelRouteView, parent: QWidget | None = None) -> None:
        super().__init__("Confirm Travel", parent)
        self.route = route
        self.setObjectName("travelConfirmationDialog")
        self.setModal(True)
        self.setMinimumWidth(470)
        layout = self.content_layout
        title = QLabel("CONFIRM JOURNEY")
        title.setObjectName("travelConfirmationTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        forward = route.target_location_id == route.destination_id
        departure_name = route.origin_name if forward else route.destination_name
        arrival_name = route.destination_name if forward else route.origin_name
        destination = QLabel(f"{departure_name}  to  {arrival_name}")
        destination.setObjectName("travelConfirmationDestination")
        destination.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(destination)
        detail = QLabel(
            f"{route.distance_miles} miles • {route.travel_minutes} minutes • "
            f"{route.stamina_cost} stamina • danger {route.danger_rating}/10\n\n"
            f"{route.description}"
        )
        detail.setObjectName("travelConfirmationDetail")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        warning = QLabel(
            "Travel advances the campaign clock. Dangerous routes may begin an encounter on arrival."
        )
        warning.setObjectName("travelConfirmationWarning")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        buttons = QHBoxLayout()
        cancel = SemanticButton("Cancel", role="secondary")
        cancel.clicked.connect(self.reject)
        confirm = SemanticButton(
            "Begin Journey", role="primary", object_name="beginJourneyButton"
        )
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)


class CampConfirmationDialog(ThemedDialog):
    def __init__(self, duration_minutes: int, parent: QWidget | None = None) -> None:
        super().__init__("Confirm Camp", parent)
        self.duration_minutes = duration_minutes
        self.setObjectName("travelConfirmationDialog")
        self.setModal(True)
        layout = self.content_layout
        title = QLabel("MAKE CAMP")
        title.setObjectName("travelConfirmationTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        detail = QLabel(
            f"Rest for {duration_minutes // 60} hours. The campaign clock will advance "
            "and eligible resources will recover."
        )
        detail.setObjectName("travelConfirmationDetail")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        buttons = QHBoxLayout()
        cancel = SemanticButton("Cancel", role="secondary")
        cancel.clicked.connect(self.reject)
        confirm = SemanticButton("Make Camp", role="primary")
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)
