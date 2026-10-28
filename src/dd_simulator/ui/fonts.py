"""Register redistributable fallback fonts shipped with the application."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFontDatabase


LOGGER = logging.getLogger(__name__)
FONT_DIRECTORY = Path(__file__).parent / "assets" / "fonts"
FONT_FILES = ("Vera.ttf", "VeraBd.ttf")


def register_application_fonts() -> tuple[str, ...]:
    """Load packaged fonts and return the registered family names."""

    families: list[str] = []
    for filename in FONT_FILES:
        path = FONT_DIRECTORY / filename
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            LOGGER.warning("Could not register application font: %s", path)
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
    return tuple(families)
