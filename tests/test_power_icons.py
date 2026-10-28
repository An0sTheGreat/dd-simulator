import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage

from dd_simulator.state.abilities import CATALOG
from dd_simulator.state.character_creation import SKILLS
from dd_simulator.ui.power_icons import (
    FALLBACK_ICON, MANIFEST_PATH, POWERS_ROOT, action_icon_path, skill_icon_path,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _resolved_icons() -> list[Path]:
    return [skill_icon_path(name) for name in SKILLS] + [action_icon_path(key) for key in CATALOG]


def _import_script():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(
            "import_power_icons", SCRIPTS / "import_power_icons.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS))
    return module


def test_every_skill_and_catalog_action_has_a_mapping() -> None:
    manifest = _manifest()

    assert sorted(manifest["skills"]) == sorted(SKILLS)
    assert sorted(manifest["actions"]) == sorted(CATALOG)


def test_every_mapped_icon_is_packaged_and_loads() -> None:
    for path in _resolved_icons():
        assert path != FALLBACK_ICON
        assert path.is_relative_to(POWERS_ROOT), path
        image = QImage(str(path))
        assert not image.isNull(), path
        assert max(image.width(), image.height()) == 128, path


def test_packaged_folder_holds_exactly_the_import_targets() -> None:
    targets = sorted(target for _, target in _import_script().import_jobs(Path("unused")))

    assert targets == sorted(_resolved_icons())
    assert sorted(POWERS_ROOT.glob("*/*.png")) == targets


def test_no_library_icon_is_used_twice() -> None:
    manifest = _manifest()
    sources = [*manifest["skills"].values(), *manifest["actions"].values()]

    assert len(sources) == len(set(sources))


def test_unknown_names_return_the_fallback() -> None:
    assert not QImage(str(FALLBACK_ICON)).isNull()
    assert skill_icon_path("Underwater Basket Weaving") == FALLBACK_ICON
    assert action_icon_path("no_such_action") == FALLBACK_ICON
