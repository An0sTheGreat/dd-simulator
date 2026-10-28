from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from dd_simulator.app import build_application
from dd_simulator.ui.themes.theme_manager import URL_PATTERN


def test_concept_b_header_has_crest_rule_small_caps_and_named_glyph_buttons(
    tmp_path: Path,
) -> None:
    app, window, themes = build_application([], config_dir=tmp_path)
    window.resize(1280, 720)
    window.show()
    app.processEvents()

    rule = window.title_bar.findChild(QWidget, "headerCrestRule")
    assert rule is not None
    crest = rule.findChild(QLabel, "headerCrest")
    halves = [rule.findChild(QLabel, name) for name in ("headerRuleLeft", "headerRuleRight")]
    assert crest is not None and None not in halves
    # The rule spans the bar and the crest sits whole and centred at 1280 px.
    assert rule.width() == window.title_bar.width()
    crest_box = crest.geometry()
    assert rule.rect().contains(crest_box)
    assert abs(crest_box.center().x() - rule.rect().center().x()) <= 1
    assert all(half.width() > 0 for half in halves)

    assert window.application_title.font().capitalization() == QFont.Capitalization.SmallCaps
    for name in ("windowMinimizeButton", "windowMaximizeButton", "windowCloseButton"):
        assert window.findChild(QPushButton, name).accessibleName()

    for theme_id in ("high_fantasy", "modern_proof"):
        stylesheet = themes.load_theme(theme_id).stylesheet
        root_rule = re.search(r"QWidget#applicationRoot\s*\{(?P<body>[^}]*)\}", stylesheet)
        assert root_rule is not None, theme_id
        background = URL_PATTERN.search(root_rule["body"])
        assert background is not None, theme_id
        assert Path(background["path"]).is_file(), theme_id

    window.close()
    app.processEvents()
