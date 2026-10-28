from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from dd_simulator.state import GameStateDatabase
from dd_simulator.state.encounters import ENEMY_ARCHETYPES
from dd_simulator.state.item_catalog import RARITIES, catalog_items
from dd_simulator.state.seed import seed_demo_campaign
import dd_simulator.state
from dd_simulator.ui import item_icons
from dd_simulator.ui.item_icons import ASSET_ROOT, LIBRARY_ROOT, icon_path, icon_records, resolve_icon


PRESETS_ROOT = Path(dd_simulator.state.__file__).parent / "presets"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _seed_item_names() -> set[tuple[str, str]]:
    database = GameStateDatabase.in_memory()
    database.initialize()
    seed_demo_campaign(database)
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT name, rarity FROM inventory_items UNION SELECT name, rarity FROM merchant_stock"
        ).fetchall()
    names = {(str(name), str(rarity)) for name, rarity in rows if name}
    for enemy in ENEMY_ARCHETYPES:
        names.update((loot, "common") for loot in enemy.loot)
    names.update((name, "common") for name in _preset_item_names())
    return names


def _preset_item_names() -> set[str]:
    """Every `name` in a list under a key containing "item" in any preset JSON."""

    names: set[str] = set()

    def walk(value: object, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, child_key)
        elif isinstance(value, list):
            for child in value:
                if "item" in key and isinstance(child, dict) and child.get("name"):
                    names.add(str(child["name"]))
                walk(child, key)

    for path in PRESETS_ROOT.glob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return names


def test_every_catalog_record_and_seed_item_resolves_to_a_packaged_icon() -> None:
    QApplication.instance() or QApplication([])
    records = icon_records()
    assert len(records) == len(catalog_items()) == 1686
    resolved = list(records) + [
        resolve_icon(name, rarity if rarity in RARITIES else "common")
        for name, rarity in sorted(_seed_item_names())
    ]
    assert len(resolved) > len(records)
    paths = {icon_path(record) for record in resolved if record is not None}
    assert None not in resolved
    assert all(path.parent == LIBRARY_ROOT and path.is_file() for path in paths)
    assert all(not QImage(str(path)).isNull() for path in paths)


def test_manifest_sources_match_the_packaged_library() -> None:
    manifest = json.loads((ASSET_ROOT / "item_icon_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["records"].values()) == set(manifest["sources"])
    assert {path.name for path in LIBRARY_ROOT.glob("*.png")} == set(manifest["sources"])


def test_resolution_is_stable_and_matches_item_type() -> None:
    first = icon_path(resolve_icon("Iron Shortsword", "common", "weapon"))
    resolve_icon.cache_clear()
    assert icon_path(resolve_icon("Iron Shortsword", "common", "weapon")) == first
    sources = json.loads((ASSET_ROOT / "item_icon_manifest.json").read_text(encoding="utf-8"))[
        "sources"
    ]

    def source(name: str, category: str) -> str:
        return sources[icon_path(resolve_icon(name, "common", category)).name]

    assert source("Iron Shortsword", "weapon").startswith("items/weapons/")
    assert source("Steel Helmet", "armor").startswith("items/armor/")
    assert source("Health Potion", "potion").split("/")[1] in {"elixir", "liquid"}


def test_legendary_records_use_different_art_than_common_siblings() -> None:
    by_subtype: dict[tuple[str, str], list] = {}
    for record in icon_records():
        by_subtype.setdefault((record.category, record.subtype), []).append(record)
    checked = 0
    for members in by_subtype.values():
        common = [record for record in members if record.visual_tier <= 1]
        legendary = [record for record in members if record.visual_tier == 4]
        if not common or not legendary or len({icon_path(r) for r in members}) < 2:
            continue
        checked += 1
        assert icon_path(min(common, key=lambda r: r.index)) not in {
            icon_path(record) for record in legendary
        }
    assert checked >= 10


def test_preset_items_resolve_to_fitting_categories() -> None:
    names = _preset_item_names()
    assert "Nullglass Edge" in names and len(names) >= 10
    resolved = {name: resolve_icon(name, "common") for name in names}
    assert all(record is not None and record.category != "misc" for record in resolved.values())
    expected = {
        "Nullglass Edge": ("weapon", "dagger"),
        "Jovian Aegis": ("armor", "shield"),
        "Stormsilk Mantle": ("armor", "cloak"),
        "Gravline Bracer": ("armor", "gloves"),
        "Starlight Injector": ("potion", "elixir"),
        "Map of Roads Not Taken": ("quest", "map"),
    }
    for name, kind in expected.items():
        assert (resolved[name].category, resolved[name].subtype) == kind, name


def test_higher_tier_records_get_more_detailed_art_in_a_pool() -> None:
    # Detail is the byte size of the packaged 128 px PNG, the metric the build script sorts by.
    for subtype in ("dagger", "shortsword", "shield", "gloves"):
        members = sorted(
            (record for record in icon_records() if record.subtype == subtype),
            key=lambda record: (record.visual_tier, record.index),
        )
        plain, ornate = members[0], members[-1]
        assert plain.visual_tier < ornate.visual_tier
        assert icon_path(plain).stat().st_size < icon_path(ornate).stat().st_size, subtype


def test_known_records_resolve_to_known_packaged_icons() -> None:
    # Pinned names catch any per-process randomness (hash seeds, set order) in the mapping.
    assert icon_path(icon_records()[0]).name == "sword-9.png"
    assert icon_path(resolve_icon("Old Iron Axe", "common", "weapon")).name == "axe-14.png"
    assert icon_path(resolve_icon("Nullglass Edge")).name == "daggers-44.png"


@pytest.mark.parametrize("mapping", [{}, {"1": "missing-icon.png"}])
def test_unmapped_or_missing_icon_yields_a_null_pixmap(monkeypatch, mapping) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(item_icons, "_library_icons", lambda: mapping)
    item_icons._record_pixmap.cache_clear()
    try:
        assert item_icons._record_pixmap(1, 32).isNull()
    finally:
        item_icons._record_pixmap.cache_clear()


@pytest.mark.parametrize("name", ["../escape.png", "C:/escape.png", "sub/../../escape.png"])
def test_importer_rejects_names_outside_the_library(monkeypatch, tmp_path, name) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    importer = importlib.import_module("import_item_icons")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": {name: "x.png"}, "records": {"0": name}}))
    monkeypatch.setattr(importer, "MANIFEST_PATH", manifest)
    with pytest.raises(SystemExit, match="escapes"):
        importer.import_jobs(tmp_path)
