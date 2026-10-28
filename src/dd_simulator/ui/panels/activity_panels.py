"""Data-driven event-log and recent-event panels for UI Phase 3."""

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import EventView
from dd_simulator.ui.panels.common import semantic_label
from dd_simulator.ui.widgets.codex_cards import make_codex_card


class EventLogPanel(QFrame):
    filter_changed = Signal(int)

    def __init__(self, events: tuple[EventView, ...]) -> None:
        super().__init__()
        self.setObjectName("eventLogPanel")
        self.content_layout = make_codex_card(self, "Event Log")
        self.content_layout.setAlignment(Qt.AlignmentFlag(0))  # the log scroll takes the height
        self.events = events
        self.filter_names = ("All", "Combat", "System", "Quests", "NPCs")
        tabs = QTabBar()
        tabs.setObjectName("eventFilterTabs")
        for name in self.filter_names:
            tabs.addTab(name)
        tabs.setCurrentIndex(0)
        tabs.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.content_layout.addWidget(tabs)
        self.tabs = tabs

        entries_widget = QWidget()
        entries_widget.setObjectName("eventEntries")
        entries_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        entries = QVBoxLayout(entries_widget)
        entries.setContentsMargins(0, 0, 0, 0)
        entries.setSpacing(4)
        entries.setAlignment(Qt.AlignmentFlag.AlignBottom)
        entries.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.entries = entries
        self.entries_widget = entries_widget
        scroll = QScrollArea()
        scroll.setObjectName("eventLogScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(entries_widget)
        self.scroll_area = scroll
        self.content_layout.addWidget(scroll, 1)
        tabs.currentChanged.connect(self._change_filter)
        self._render_events(events)
        QTimer.singleShot(0, self.scroll_to_latest)

    def _render_events(self, events: tuple[EventView, ...]) -> None:
        while self.entries.count():
            item = self.entries.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not events:
            empty = semantic_label("No recorded events", text_role="muted")
            empty.setObjectName("eventLogEmptyState")
            empty.setToolTip("Events will appear here as turns are recorded")
            self.entries.addWidget(empty)
        else:
            for event in events:
                label = semantic_label(event.summary, text_role=event.category, word_wrap=True)
                label.setObjectName("eventLogEntry")
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setToolTip(f"{event.time_label} - {event.category.title()}")
                label.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
                )
                self.entries.addWidget(label)

    def _change_filter(self, index: int) -> None:
        name = self.filter_names[index].lower()
        aliases = {"quests": "quest", "npcs": "npc"}
        category = aliases.get(name, name)
        filtered = (
            self.events
            if category == "all"
            else tuple(event for event in self.events if event.category == category)
        )
        self._render_events(filtered)
        QTimer.singleShot(0, self.scroll_to_latest)
        self.filter_changed.emit(index)

    def set_current_filter(self, index: int) -> None:
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def current_filter(self) -> int:
        return self.tabs.currentIndex()

    def scroll_state(self) -> tuple[int, bool]:
        bar = self.scroll_area.verticalScrollBar()
        return bar.value(), bar.value() >= bar.maximum() - 2

    def restore_scroll_state(self, state: tuple[int, bool]) -> None:
        value, was_at_bottom = state
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum() if was_at_bottom else min(value, bar.maximum()))

    def scroll_to_latest(self) -> None:
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())


class RecentEventsPanel(QFrame):
    def __init__(self, events: tuple[EventView, ...]) -> None:
        super().__init__()
        self.setObjectName("recentEventsPanel")
        self.content_layout = make_codex_card(self, "Recent Events", count=len(events))
        self.content_layout.setAlignment(Qt.AlignmentFlag(0))
        entries_widget = QWidget()
        entries_widget.setObjectName("recentEventEntries")
        entries_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        entries = QVBoxLayout(entries_widget)
        entries.setContentsMargins(0, 0, 0, 0)
        entries.setSpacing(6)
        entries.setAlignment(Qt.AlignmentFlag.AlignBottom)
        entries.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        if not events:
            empty = semantic_label("No recent events", text_role="muted")
            empty.setObjectName("recentEventsEmptyState")
            empty.setToolTip("Recent events will appear after play begins")
            entries.addWidget(empty)
        else:
            for event in events:
                row = QVBoxLayout()
                row.setSpacing(1)
                row.addWidget(semantic_label(event.time_label, text_role="muted"))
                summary = semantic_label(event.summary, text_role="secondary", word_wrap=True)
                summary.setObjectName("recentEventEntry")
                summary.setTextFormat(Qt.TextFormat.PlainText)
                summary.setProperty("eventCategory", event.category)
                summary.setToolTip(event.category.title())
                summary.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
                )
                row.addWidget(summary)
                entries.addLayout(row)
        scroll = QScrollArea()
        scroll.setObjectName("recentEventsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(entries_widget)
        self.scroll_area = scroll
        self.content_layout.addWidget(scroll, 1)
        QTimer.singleShot(0, self.scroll_to_latest)

    def scroll_state(self) -> tuple[int, bool]:
        bar = self.scroll_area.verticalScrollBar()
        return bar.value(), bar.value() >= bar.maximum() - 2

    def restore_scroll_state(self, state: tuple[int, bool]) -> None:
        value, was_at_bottom = state
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum() if was_at_bottom else min(value, bar.maximum()))

    def scroll_to_latest(self) -> None:
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())
