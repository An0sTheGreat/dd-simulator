"""Narrative and active-quest panels for the Phase 3 screen."""

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import NarrativeView, QuestListItemView, QuestView
from dd_simulator.state.turns import normalize_narrative_segment
from dd_simulator.ui.panels.common import (
    DashboardPanel,
    highlight_recent_turn,
    semantic_label,
)
from dd_simulator.ui.widgets.quest_list import QuestListWidget
from dd_simulator.ui.widgets.semantic_button import SemanticButton


class ResponseHoverCard(QFrame):
    """Persistent themed card for a clipped generated response."""

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("responseHoverCard")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        self.message_label = QLabel(text)
        self.message_label.setObjectName("responseHoverText")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

    def show_near(self, global_position: QPoint) -> None:
        screen = QApplication.screenAt(global_position) or QApplication.primaryScreen()
        maximum_width = 640
        if screen is not None:
            maximum_width = min(maximum_width, screen.availableGeometry().width() // 2)
        natural_width = self.message_label.fontMetrics().horizontalAdvance(
            self.message_label.text()
        ) + 20
        self.setFixedWidth(max(120, min(natural_width, maximum_width)))
        self.adjustSize()
        position = global_position + QPoint(14, 18)
        if screen is not None:
            bounds = screen.availableGeometry()
            position.setX(
                max(bounds.left(), min(position.x(), bounds.right() - self.width() + 1))
            )
            position.setY(
                max(bounds.top(), min(position.y(), bounds.bottom() - self.height() + 1))
            )
        self.move(position)
        self.show()
        self.raise_()


class ResponseOptionButton(SemanticButton):
    """Suggested action button with a full-text card only when clipped."""

    def __init__(self, text: str) -> None:
        super().__init__(
            text,
            role="secondary",
            object_name="suggestedActionButton",
        )
        self.setAccessibleDescription("Choose and immediately send this response")
        self.hover_card: ResponseHoverCard | None = None
        self._hover_suppressed = False
        self.clicked.connect(self.dismiss_hover_card)

    def is_text_clipped(self) -> bool:
        available_width = max(0, self.contentsRect().width() - 12)
        return self.fontMetrics().horizontalAdvance(self.text()) > available_width

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.isEnabled() and self.is_text_clipped() and not self._hover_suppressed:
            self.hover_card = ResponseHoverCard(self.text(), self)
            self.hover_card.show_near(QCursor.pos())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._close_hover_card()
        self._hover_suppressed = False
        super().leaveEvent(event)

    def dismiss_hover_card(self) -> None:
        self._hover_suppressed = True
        self._close_hover_card()

    def _close_hover_card(self) -> None:
        if self.hover_card is not None:
            self.hover_card.close()
            self.hover_card.deleteLater()
            self.hover_card = None

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self.is_text_clipped():
            self._close_hover_card()
        super().resizeEvent(event)


class NarrativePanel(DashboardPanel):
    submission_requested = Signal(str)
    cancellation_requested = Signal()
    retry_requested = Signal(str)

    def __init__(self, data: NarrativeView) -> None:
        super().__init__("narrativePanel", "NARRATIVE & PLAYER ACTION")

        scroll = QScrollArea()
        scroll.setObjectName("narrativeScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        history = QWidget()
        history.setObjectName("narrativeHistory")
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(2, 2, 6, 2)
        history_layout.setSpacing(9)
        self.latest_turn_widgets: list[QWidget] = []
        latest_player_index = max(
            (
                index
                for index, message in enumerate(data.messages)
                if message.kind == "player"
            ),
            default=-1,
        )
        history_layout.addWidget(
            semantic_label(data.title, object_name="sceneTitle", text_role="accent")
        )
        if data.messages:
            for index, message in enumerate(data.messages):
                if message.kind == "player":
                    label = semantic_label(
                        f"You: {message.text}",
                        object_name="playerActionHistory",
                        text_role="playerAction",
                        word_wrap=True,
                    )
                    history_layout.addWidget(label)
                    if index >= latest_player_index:
                        self.latest_turn_widgets.append(label)
                else:
                    for segment in normalize_narrative_segment(
                        message.kind,
                        message.text,
                    ):
                        label = semantic_label(
                            segment.text,
                            object_name=f"{segment.kind}Message{index}",
                            text_role=segment.kind,
                            word_wrap=True,
                        )
                        history_layout.addWidget(label)
                        if latest_player_index >= 0 and index > latest_player_index:
                            self.latest_turn_widgets.append(label)
        elif data.player_action:
            history_layout.addWidget(
                semantic_label(
                    f"You: {data.player_action}",
                    object_name="playerActionHistory",
                    text_role="playerAction",
                    word_wrap=True,
                )
            )
        if not data.messages and data.response_segments:
            for index, segment in enumerate(data.response_segments):
                for normalized in normalize_narrative_segment(
                    segment.kind,
                    segment.text,
                ):
                    history_layout.addWidget(
                        semantic_label(
                            normalized.text,
                            object_name=f"{normalized.kind}Message{index}",
                            text_role=normalized.kind,
                            word_wrap=True,
                        )
                    )
        elif not data.messages:
            history_layout.addWidget(
                semantic_label(
                    "\n\n".join(data.paragraphs),
                    text_role="narrative",
                    word_wrap=True,
                )
            )
            history_layout.addWidget(
                semantic_label(
                    data.dialogue,
                    object_name="spokenMessage",
                    text_role="spoken",
                    word_wrap=True,
                )
            )
        history_layout.addWidget(
            semantic_label(data.prompt, object_name="actionPrompt", text_role="warning")
        )
        history_layout.addStretch(1)
        scroll.setWidget(history)
        self.history_scroll = scroll
        self.content_layout.addWidget(scroll, 1)
        QTimer.singleShot(0, self.scroll_to_latest)

        suggestions = QGridLayout()
        suggestions.setSpacing(5)
        self.suggestion_buttons: list[ResponseOptionButton] = []
        for index, action in enumerate(data.suggested_actions):
            button = ResponseOptionButton(action)
            button.setMinimumHeight(28)
            button.clicked.connect(
                lambda _checked=False, value=action: self._choose_suggestion(value)
            )
            self.suggestion_buttons.append(button)
            suggestions.addWidget(button, index // 3, index % 3)
        for column in range(3):
            suggestions.setColumnStretch(column, 1)
        self.content_layout.addLayout(suggestions)

        action_row = QHBoxLayout()
        action_input = QLineEdit()
        action_input.setObjectName("playerActionInput")
        action_input.setAccessibleName("Player action")
        action_input.setPlaceholderText("Type your action...")
        action_input.setMaxLength(2000)
        action_input.setToolTip("Submit a non-combat action for local model resolution")
        action_input.returnPressed.connect(self._request_submission)
        submit = SemanticButton(
            "Send",
            role="primary",
            object_name="submitActionButton",
        )
        submit.clicked.connect(self._request_submission)
        self.action_input = action_input
        self.submit_button = submit
        action_row.addWidget(action_input, 1)
        action_row.addWidget(submit)

        cancel = SemanticButton("Cancel", role="destructive", object_name="cancelActionButton")
        cancel.setToolTip("Cancel this turn; generated changes will not be committed")
        cancel.clicked.connect(self._request_cancellation)
        cancel.setVisible(False)
        self.cancel_button = cancel
        action_row.addWidget(cancel)

        retry = SemanticButton("Retry", role="secondary", object_name="retryActionButton")
        retry.setToolTip("Retry the unchanged player action")
        retry.clicked.connect(lambda: self.retry_requested.emit(self.action_input.text()))
        retry.setVisible(False)
        self.retry_button = retry
        action_row.addWidget(retry)
        self.content_layout.addLayout(action_row)

        self.feedback = semantic_label("", object_name="actionFeedback", text_role="muted")
        self.feedback.setAccessibleName("Action submission feedback")
        self.content_layout.addWidget(self.feedback)

    def highlight_latest_turn(self, *, reduced_motion: bool) -> None:
        highlight_recent_turn(
            self,
            self.latest_turn_widgets,
            reduced_motion=reduced_motion,
        )

    def set_combat_active(self, active: bool) -> None:
        self.action_input.setEnabled(not active)
        self.submit_button.setEnabled(not active)
        for button in self.suggestion_buttons:
            button.setEnabled(not active)
        if active:
            self.action_input.setPlaceholderText("Use the Combat tab while an encounter is active")
            self.action_input.setToolTip(
                "Combat actions are validated through the deterministic Combat tab"
            )

    def scroll_to_latest(self) -> None:
        bar = self.history_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _choose_suggestion(self, text: str) -> None:
        self.action_input.setText(text)
        self.submission_requested.emit(text)

    def _request_submission(self) -> None:
        self.submission_requested.emit(self.action_input.text())

    def _request_cancellation(self) -> None:
        self.cancel_button.setEnabled(False)
        self.feedback.setProperty("feedbackState", "warning")
        self.feedback.setText("Cancelling after the local model returns; no turn will be committed...")
        self._refresh_feedback_style()
        self.cancellation_requested.emit()

    def show_submission_feedback(self, text: str) -> None:
        self.action_input.clear()
        self.action_input.setProperty("validationState", "valid")
        self.feedback.setProperty("feedbackState", "success")
        self.feedback.setText(f"Local action accepted: {text}")
        self._refresh_feedback_style()

    def show_validation_error(self, message: str) -> None:
        self.action_input.setProperty("validationState", "error")
        self.feedback.setProperty("feedbackState", "error")
        self.feedback.setText(message)
        self._refresh_feedback_style()
        self.action_input.setFocus()

    def show_resolution_pending(self, action: str) -> None:
        self.action_input.setText(action)
        self.action_input.setEnabled(False)
        self.submit_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self.retry_button.setVisible(False)
        self.feedback.setProperty("feedbackState", "warning")
        self.feedback.setText("Resolving this non-combat action with the local model...")
        self._refresh_feedback_style()

    def show_resolution_error(self, message: str) -> None:
        self.action_input.setEnabled(True)
        self.submit_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.retry_button.setVisible(True)
        self.feedback.setProperty("feedbackState", "error")
        self.feedback.setText(message)
        self._refresh_feedback_style()
        self.action_input.setFocus()

    def show_resolution_cancelled(self) -> None:
        self.action_input.setEnabled(True)
        self.submit_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.retry_button.setVisible(True)
        self.feedback.setProperty("feedbackState", "warning")
        self.feedback.setText("Action cancelled; no state was changed.")
        self._refresh_feedback_style()
        self.action_input.setFocus()

    def reset_resolution_controls(self) -> None:
        self.action_input.clear()
        self.action_input.setEnabled(True)
        self.submit_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.retry_button.setVisible(False)
        self.feedback.setText("")
        self.feedback.setProperty("feedbackState", "")
        self._refresh_feedback_style()

    def _refresh_feedback_style(self) -> None:
        for widget in (self.action_input, self.feedback):
            widget.style().unpolish(widget)
            widget.style().polish(widget)


class QuestObjectivePanel(DashboardPanel):
    tab_changed = Signal(int)

    def __init__(
        self,
        data: QuestView,
        quest_list: tuple[QuestListItemView, ...],
    ) -> None:
        super().__init__("questObjectivePanel", "QUESTS & OBJECTIVES")

        tabs = QTabBar()
        tabs.setObjectName("questTabs")
        tabs.addTab("Objectives")
        tabs.addTab("Quests")
        tabs.addTab("Journal")
        tabs.setCurrentIndex(0)
        tabs.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.content_layout.addWidget(tabs)
        self.tabs = tabs
        self.content_layout.addWidget(
            semantic_label(data.status.upper(), text_role="success")
        )
        self.content_layout.addWidget(
            semantic_label(data.title, object_name="activeQuestTitle", text_role="accent")
        )
        self.content_layout.addWidget(
            semantic_label(data.summary, text_role="secondary", word_wrap=True)
        )

        stack = QStackedWidget()
        stack.setObjectName("questPageStack")
        self.stack = stack

        objective_page = QWidget()
        objective_page.setObjectName("objectivesPage")
        objectives = QVBoxLayout(objective_page)
        objectives.setContentsMargins(0, 0, 0, 0)
        objectives.setSpacing(5)
        for objective in data.objectives:
            text = f"Optional: {objective.text}" if objective.optional else objective.text
            item = QCheckBox(text)
            item.setObjectName("objectiveItem")
            item.setProperty("objectiveState", "complete" if objective.completed else "active")
            item.setChecked(objective.completed)
            item.setEnabled(False)
            item.setToolTip("Static objective preview")
            objectives.addWidget(item)
        objectives.addStretch(1)
        stack.addWidget(objective_page)

        quest_page = QWidget()
        quest_page.setObjectName("questLogPage")
        quest_layout = QVBoxLayout(quest_page)
        quest_layout.setContentsMargins(0, 0, 0, 0)
        quest_layout.addWidget(
            semantic_label("QUEST LOG", object_name="questLogTitle", text_role="accent")
        )
        quest_layout.addWidget(QuestListWidget(quest_list), 1)
        stack.addWidget(quest_page)

        journal_page = QWidget()
        journal_page.setObjectName("journalPreviewPage")
        journal_layout = QVBoxLayout(journal_page)
        journal_layout.setContentsMargins(0, 0, 0, 0)
        journal_layout.addWidget(
            semantic_label(
                "Journal entries will be populated from committed campaign events.",
                text_role="muted",
                word_wrap=True,
            )
        )
        journal_layout.addStretch(1)
        stack.addWidget(journal_page)

        tabs.currentChanged.connect(self._change_tab)
        self.content_layout.addWidget(stack, 1)

    def _change_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.tab_changed.emit(index)

    def set_current_tab(self, index: int) -> None:
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def current_tab(self) -> int:
        return self.tabs.currentIndex()
