from functools import cache
import importlib.util
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _import_script():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "check_scene_contrast", PROJECT_ROOT / "scripts" / "check_scene_contrast.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = _import_script()
# one test per image, so parallel workers share the work (about 11 s in all)
IMAGE_PATHS = SCRIPT.image_paths()
theme_colors = cache(SCRIPT.theme_colors)


def test_every_packaged_location_image_is_checked() -> None:
    assert len(IMAGE_PATHS) >= 90
    assert {"high_fantasy", "modern_proof"} <= set(theme_colors())


@pytest.mark.parametrize("path", IMAGE_PATHS, ids=lambda path: f"{path.parent.name}/{path.stem}")
def test_narration_keeps_4_5_contrast_over_every_location_image(path: Path) -> None:
    _app = QApplication.instance() or QApplication([])
    for theme_id, (overlay, narrator) in theme_colors().items():
        ratio = SCRIPT.contrast(SCRIPT.luminance(narrator), SCRIPT.band_luminance(path, overlay))
        assert ratio >= SCRIPT.MINIMUM, f"{theme_id} {path.parent.name}/{path.name}: {ratio:.2f}:1"


def test_narrator_colour_regex_skips_background_color() -> None:
    script = SCRIPT
    qss = "QLabel#conversationNarrator { background-color: #ffffff; color: #123456; }"
    assert script.NARRATOR_COLOR.search(qss).group(1) == "#123456"
