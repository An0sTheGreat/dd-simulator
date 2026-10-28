"""Phase 4a: the Concept T ConversationView."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect

from dd_simulator.ui.models.presentation import NarrativeMessageView, TurnNoteView
from dd_simulator.ui.widgets.conversation_view import ConversationView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _view(*, reduced_motion: bool = False) -> ConversationView:
    _app()
    view = ConversationView(reduced_motion=reduced_motion)
    view.resize(800, 470)
    view.show()
    QApplication.processEvents()
    return view


def _turns(first: int, count: int) -> tuple[NarrativeMessageView, ...]:
    messages: list[NarrativeMessageView] = []
    for turn in range(first, first + count):
        messages.append(NarrativeMessageView("player", f"I act on turn {turn}.", turn))
        messages.append(NarrativeMessageView(
            "narrative", f"The world answers turn {turn} with a long, winding reply " * 3, turn,
        ))
    return tuple(messages)


def test_each_kind_renders_with_its_role_and_styled_object_names() -> None:
    view = _view()
    view.set_messages((
        NarrativeMessageView("narrative", "The road winds south.", 1),
        NarrativeMessageView("monologue", "You wonder about the cart.", 1),
        NarrativeMessageView("player", "<b>I wave.</b>", 1),
        NarrativeMessageView("spoken", "Trouble with bandits.", 1, speaker_id="npc-hedrin",
                             speaker_name="Hedrin", speaker_portrait="missing.png"),
    ), False)
    narrator, monologue, player, npc = view.rows
    assert (narrator.role, narrator.text_label.objectName()) == ("narrator", "conversationNarrator")
    assert monologue.role == "narrator" and monologue.text_label.property("messageKind") == "monologue"
    assert (player.role, player.box.objectName()) == ("player", "conversationPlayer")
    assert player.text_label.text() == "<b>I wave.</b>"  # plain text, never rich text
    assert (npc.role, npc.box.objectName()) == ("npc", "conversationNpc")
    assert npc.speaker_label is not None and npc.speaker_label.text() == "Hedrin"
    assert npc.portrait is not None and npc.portrait.property("placeholder") is True
    assert player.speaker_label is None  # the player box has no name label
    # Transparent: the view paints nothing of its own, and the viewport carries the top fade.
    assert not view.viewport().autoFillBackground() and not view.widget().autoFillBackground()
    assert isinstance(view.viewport().graphicsEffect(), QGraphicsOpacityEffect)


def test_unnamed_speaker_gets_the_neutral_placeholder() -> None:
    view = _view()
    view.set_messages((NarrativeMessageView("spoken", "Who goes there?", 1),), False)
    (row,) = view.rows
    assert row.role == "npc" and row.speaker_label is None
    assert row.portrait is not None and row.portrait.property("placeholder") is True
    assert row.portrait.text() == ""


def test_notes_attach_under_their_message_and_align_by_kind() -> None:
    view = _view()
    view.set_messages((
        NarrativeMessageView("player", "I head south.", 1,
                             notes=(TurnNoteView("travel", "Travelled 6 mi · 2 h"),)),
        NarrativeMessageView("spoken", "Take it.", 2, speaker_name="Hedrin",
                             notes=(TurnNoteView("xp", "+50 XP"), TurnNoteView("item", "Iron Dagger added"))),
    ), False)
    layout = view.widget().layout()
    order = [layout.itemAt(index).widget() for index in range(1, layout.count())]
    player, player_notes, npc, npc_notes = order
    assert player is view.rows[0] and npc is view.rows[1]
    assert player_notes.alignment == "right" and player_notes.layout().contentsMargins().left() == 0
    assert npc_notes.alignment == "indent" and npc_notes.layout().contentsMargins().left() == 48
    assert [(t.property("noteKind"), t.text()) for t in npc_notes.tags] == [
        ("xp", "+50 XP"), ("item", "Iron Dagger added"),
    ]


def test_reaching_the_top_requests_older_once_per_page() -> None:
    view = _view(reduced_motion=True)
    view.set_messages(_turns(41, 20), True)
    spy = QSignalSpy(view.older_requested)
    bar = view.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == bar.maximum()
    bar.setValue(0)
    bar.setValue(40)
    bar.setValue(0)
    assert spy.count() == 1 and spy.at(0) == [41]
    view.prepend_messages(_turns(21, 20), True)
    bar.setValue(0)
    assert spy.count() == 2 and spy.at(1) == [21]


def test_prepend_keeps_the_top_item_at_the_same_viewport_y() -> None:
    view = _view(reduced_motion=True)
    view.set_messages(_turns(41, 20), True)
    bar = view.verticalScrollBar()
    bar.setValue(bar.maximum() // 3)
    viewport = view.viewport()
    anchor = next(row for row in view.rows if row.mapTo(viewport, row.rect().bottomLeft()).y() > 0)
    before = anchor.mapTo(viewport, anchor.rect().topLeft()).y()
    view.prepend_messages(_turns(21, 20), True)
    QApplication.processEvents()
    after = anchor.mapTo(viewport, anchor.rect().topLeft()).y()
    assert abs(after - before) <= 2, (before, after)
    assert view.rows[0].message.turn_number == 21


def test_append_turn_scrolls_smoothly_to_the_newest_message() -> None:
    view = _view()
    view.set_messages(_turns(1, 10), False)
    view.verticalScrollBar().setValue(0)
    view.append_turn(_turns(11, 1))
    assert view.scroll_animation.state() == QAbstractAnimation.State.Running
    assert view.emphasis_animating
    assert all(row.property("recentTurn") for row in view.recent_rows)
    view.scroll_animation.setCurrentTime(view.scroll_animation.duration())
    bar = view.verticalScrollBar()
    assert bar.value() == bar.maximum()


def test_reduced_motion_jumps_and_keeps_a_static_emphasis() -> None:
    view = _view(reduced_motion=True)
    view.set_messages(_turns(1, 10), False)
    view.verticalScrollBar().setValue(0)
    view.append_turn(_turns(11, 1))
    bar = view.verticalScrollBar()
    assert view.scroll_animation.state() == QAbstractAnimation.State.Stopped
    assert bar.value() == bar.maximum()
    assert not view.emphasis_animating
    assert [row.message.turn_number for row in view.recent_rows] == [11, 11]
    assert all(row.property("recentTurn") and row.box.graphicsEffect() is None
               for row in view.recent_rows if row.role != "narrator")
    view.clear_emphasis()
    assert not view.recent_rows
