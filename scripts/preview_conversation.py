"""Render the Concept T conversation over the road art to artifacts/previews for visual review."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from dd_simulator.state import GameStateDatabase, GameStateService  # noqa: E402
from dd_simulator.ui.fonts import register_application_fonts  # noqa: E402
from dd_simulator.ui.models.presentation import NarrativeMessageView, TurnNoteView  # noqa: E402
from dd_simulator.ui.themes.theme_manager import ThemeManager  # noqa: E402
from dd_simulator.ui.widgets.conversation_view import ConversationView  # noqa: E402

UI = ROOT / "src" / "dd_simulator" / "ui"
ART = UI / "assets" / "location" / "road" / "road_daylight.png"
WIDTH, HEIGHT = 800, 470
# The mockup's vista is ~870 px tall and the conversation sits ~250 px from its top.
VISTA_HEIGHT, OFFSET = 870, 250
GRADIENT = ((0.0, 0.35), (0.12, 0.0), (0.36, 0.25), (0.62, 0.86), (0.82, 1.0))


class Backdrop(QWidget):
    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        art = QPixmap(str(ART))
        scaled = art.scaled(WIDTH, VISTA_HEIGHT, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
        x = (WIDTH - scaled.width()) // 2
        y = int((VISTA_HEIGHT - scaled.height()) * 0.3) - OFFSET
        painter.drawPixmap(x, y, scaled)
        gradient = QLinearGradient(0, -OFFSET, 0, VISTA_HEIGHT - OFFSET)
        for stop, alpha in GRADIENT:
            gradient.setColorAt(stop, QColor(18 if stop == 0.82 else 14, 14 if stop == 0.82 else 11, 10 if stop == 0.82 else 8, int(alpha * 255)))
        painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), gradient)
        painter.end()


def synthetic_turns(start: int, portrait: str) -> tuple[NarrativeMessageView, ...]:
    return (
        NarrativeMessageView("narrative", "You break camp on the Northern Ridge as dawn burns off the mist. Six goblin cairns mark where last night's ambush ended.", start),
        NarrativeMessageView("player", "I follow the old road south toward Greystone, watching the treeline.", start,
                             notes=(TurnNoteView("travel", "Travelled 6 mi · 2 h"), TurnNoteView("resource", "−4 stamina · recovered"))),
        NarrativeMessageView("narrative", "The road winds through rolling green hills, the distant walls of Greystone Keep pale on the horizon. A merchant's cart rests beneath a canvas awning beside the road, one wheel cracked clean through. The merchant straightens as you approach, one hand resting near a cudgel.", start + 1),
        NarrativeMessageView("player", "I raise a hand in greeting and walk over slowly, keeping my bow slung. “Trouble with the wheel?”", start + 1),
        NarrativeMessageView("spoken", "“Trouble with bandits, more like. They took my spare axle three nights past — and a lord's sealed chest with it. Found this blade in the ditch after. Yours, if you'll hear me out.”", start + 1,
                             speaker_id="npc-hedrin", speaker_name="Hedrin", speaker_portrait=portrait,
                             notes=(TurnNoteView("xp", "+50 XP"), TurnNoteView("item", "Iron Dagger added"),
                                    TurnNoteView("quest", "Quest updated · The Lost Heirloom"), TurnNoteView("relationship", "Hedrin +2"))),
    )


def main() -> int:
    app = QApplication.instance() or QApplication([])
    register_application_fonts()
    service = GameStateService(GameStateDatabase.in_memory())
    service.initialize()
    demo = service.load_active_dashboard().narrative.messages
    portrait = str(sorted((UI / "assets" / "codex" / "portraits" / "fantasy").glob("*.png"))[0])
    messages = (*demo, *synthetic_turns(max((m.turn_number for m in demo), default=0) + 1, portrait))
    out = ROOT / "artifacts" / "previews"
    out.mkdir(parents=True, exist_ok=True)
    manager = ThemeManager(themes_root=UI / "themes", preferences_path=out / "preview-prefs.json", default_theme_id="high_fantasy")
    for theme in ("high_fantasy", "modern_proof"):
        manager.apply_loaded_theme(app, manager.load_theme(theme), persist=False)
        backdrop = Backdrop()
        layout = QVBoxLayout(backdrop)
        layout.setContentsMargins(0, 0, 0, 0)
        view = ConversationView(reduced_motion=True)
        layout.addWidget(view)
        backdrop.resize(WIDTH, HEIGHT)
        backdrop.show()
        app.processEvents()
        view.set_messages(messages, True)
        app.processEvents()
        path = out / f"conversation-{theme}.png"
        backdrop.grab().save(str(path))
        backdrop.close()
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
