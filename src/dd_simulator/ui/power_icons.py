"""Resolve packaged skill, ability and spell icons through the power icon manifest."""

from __future__ import annotations

from functools import cache
import json
from pathlib import Path


ICON_ROOT = Path(__file__).parent / "assets" / "icons"
MANIFEST_PATH = ICON_ROOT / "power_icon_manifest.json"
POWERS_ROOT = ICON_ROOT / "powers"
FALLBACK_ICON = Path(__file__).parent / "assets" / "codex" / "ui_slot_frame.png"


def skill_icon_path(name: str) -> Path:
    """Return the packaged icon for a skill name, or the neutral fallback."""

    return _resolve("skills", name)


def action_icon_path(key: str) -> Path:
    """Return the packaged icon for an ability or spell catalog key, or the fallback."""

    if key == "attack":  # the hotbar's weapon attack wears the Attack skill's icon
        return skill_icon_path("Attack")
    return _resolve("actions", key)


@cache
def _manifest() -> dict[str, dict[str, str]]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _resolve(section: str, key: str) -> Path:
    if key in _manifest()[section]:
        path = POWERS_ROOT / section / f"{key.casefold()}.png"
        if path.is_file():
            return path
    return FALLBACK_ICON
