from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from dd_simulator.ui.themes.theme_manager import ThemeManager


THEMES_ROOT = (
    Path(__file__).parents[1]
    / "src"
    / "dd_simulator"
    / "ui"
    / "themes"
)


def manager(tmp_path: Path) -> ThemeManager:
    return ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )


def test_discovers_installed_themes(tmp_path: Path) -> None:
    discovered = manager(tmp_path).discover()
    assert set(discovered) == {"high_fantasy", "modern_proof"}


def test_stylesheets_compile_without_unresolved_tokens(tmp_path: Path) -> None:
    discovered = manager(tmp_path).discover()
    for loaded in discovered.values():
        assert "{{" not in loaded.stylesheet
        assert "background-color:" in loaded.stylesheet
        assert "QFrame#itemHoverCard, QFrame#responseHoverCard" in loaded.stylesheet


def test_supported_themes_style_the_item_hover_surface(tmp_path: Path) -> None:
    discovered = manager(tmp_path).discover()
    for loaded in discovered.values():
        assert "QFrame#itemHoverSurface" in loaded.stylesheet
        assert "QFrame#itemHoverCard {" in loaded.stylesheet


def test_simple_theme_display_names_keep_stable_ids(tmp_path: Path) -> None:
    discovered = manager(tmp_path).discover()
    assert discovered["high_fantasy"].definition.name == "Modern Fantasy Simple"
    assert discovered["modern_proof"].definition.name == "Modern Dark Simple"


def test_monologue_matches_narrative_size_across_themes(tmp_path: Path) -> None:
    for loaded in manager(tmp_path).discover().values():
        blocks = {
            role: re.search(
                rf'QLabel\[textRole="{role}"\]\s*\{{(?P<body>[^}}]+)\}}',
                loaded.stylesheet,
            )
            for role in ("narrative", "monologue")
        }
        assert all(blocks.values())
        narrative = blocks["narrative"].group("body")
        monologue = blocks["monologue"].group("body")
        size = re.compile(r"font-size:\s*([^;]+)")
        assert size.search(monologue).group(1) == size.search(narrative).group(1)
        assert "font-style: italic" in monologue
        assert "color:" in monologue


def test_missing_theme_falls_back_to_high_fantasy(tmp_path: Path) -> None:
    loaded = manager(tmp_path).load_theme("not_installed")
    assert loaded.definition.theme_id == "high_fantasy"


def test_saved_theme_preference_round_trips(tmp_path: Path) -> None:
    theme_manager = manager(tmp_path)
    theme_manager.save_preference("modern_proof")
    assert theme_manager.load_preferred_theme().definition.theme_id == "modern_proof"
    assert json.loads(theme_manager.preferences_path.read_text(encoding="utf-8")) == {
        "theme_id": "modern_proof"
    }


def test_saved_theme_preserves_ui_preferences(tmp_path: Path) -> None:
    theme_manager = manager(tmp_path)
    theme_manager.preferences_path.write_text(
        json.dumps({"ui": {"utility_tab": 2}}),
        encoding="utf-8",
    )

    theme_manager.save_preference("modern_proof")

    assert json.loads(theme_manager.preferences_path.read_text(encoding="utf-8")) == {
        "ui": {"utility_tab": 2},
        "theme_id": "modern_proof",
    }


def test_corrupt_preference_falls_back_safely(tmp_path: Path) -> None:
    theme_manager = manager(tmp_path)
    theme_manager.preferences_path.write_text("not-json", encoding="utf-8")
    assert theme_manager.load_preferred_theme().definition.theme_id == "high_fantasy"


def test_removed_default_preference_falls_back_to_modern_fantasy(tmp_path: Path) -> None:
    theme_manager = manager(tmp_path)
    theme_manager.preferences_path.write_text(
        json.dumps({"theme_id": "default"}), encoding="utf-8"
    )
    assert theme_manager.load_preferred_theme().definition.theme_id == "high_fantasy"


def test_missing_asset_or_manifest_directory_is_ignored(tmp_path: Path) -> None:
    invalid_root = tmp_path / "themes"
    invalid_root.mkdir()
    (invalid_root / "broken").mkdir()
    theme_manager = ThemeManager(
        themes_root=invalid_root,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    assert theme_manager.discover() == {}


def test_asset_resolution_uses_default_theme_fallback(tmp_path: Path) -> None:
    themes_root = tmp_path / "themes"
    shutil.copytree(THEMES_ROOT, themes_root)
    expected = themes_root / "high_fantasy" / "assets" / "panel_frame.png"
    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.write_bytes(b"phase-one-placeholder")
    theme_manager = ThemeManager(
        themes_root=themes_root,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )

    modern = theme_manager.load_theme("modern_proof")
    assert theme_manager.resolve_asset_path(modern, "panel_frame") == expected.resolve()
    assert theme_manager.resolve_asset_path(modern, "not_defined") is None


def test_theme_change_listeners_receive_applied_theme(tmp_path: Path) -> None:
    class StylesheetRecorder:
        stylesheet = ""

        def setStyleSheet(self, stylesheet: str) -> None:
            self.stylesheet = stylesheet

    received: list[str] = []
    theme_manager = manager(tmp_path)
    theme_manager.add_change_listener(
        lambda loaded: received.append(loaded.definition.theme_id)
    )
    target = StylesheetRecorder()

    theme_manager.apply_theme(target, "modern_proof")

    assert received == ["modern_proof"]
    assert "background-color:" in target.stylesheet


def test_font_scale_applies_live_and_survives_theme_change(tmp_path: Path) -> None:
    class StylesheetRecorder:
        stylesheet = ""

        def setStyleSheet(self, stylesheet: str) -> None:
            self.stylesheet = stylesheet

    theme_manager = manager(tmp_path)
    target = StylesheetRecorder()
    theme_manager.apply_loaded_theme(
        target,
        theme_manager.load_theme("high_fantasy"),
        persist=False,
    )
    assert "font-size: 13px" in target.stylesheet

    theme_manager.set_font_scale(target, 1.15)
    assert "font-size: 15px" in target.stylesheet
    assert "font-size: 10px; /* font-scale-fixed */" in target.stylesheet
    assert "font-size: 12px; /* font-scale-fixed */" in target.stylesheet
    theme_manager.apply_theme(target, "modern_proof")
    assert "font-size: 15px" in target.stylesheet
    assert "font-size: 10px; /* font-scale-fixed */" in target.stylesheet
