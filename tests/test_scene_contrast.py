import importlib.util
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _import_script():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "check_scene_contrast", PROJECT_ROOT / "scripts" / "check_scene_contrast.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_narration_keeps_4_5_contrast_over_every_location_image() -> None:
    _app = QApplication.instance() or QApplication([])
    script = _import_script()
    colors = script.theme_colors()
    assert {"high_fantasy", "modern_proof"} <= set(colors)
    paths = script.image_paths()
    assert len(paths) >= 90  # every packaged location image (about 11 s for both themes)
    for theme_id, (overlay, narrator) in colors.items():
        for path in paths:
            ratio = script.contrast(script.luminance(narrator), script.band_luminance(path, overlay))
            assert ratio >= script.MINIMUM, f"{theme_id} {path.parent.name}/{path.name}: {ratio:.2f}:1"


def test_narrator_colour_regex_skips_background_color() -> None:
    script = _import_script()
    qss = "QLabel#conversationNarrator { background-color: #ffffff; color: #123456; }"
    assert script.NARRATOR_COLOR.search(qss).group(1) == "#123456"
