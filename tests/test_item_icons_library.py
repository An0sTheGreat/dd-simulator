from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from dd_simulator.state import GameStateDatabase
from dd_simulator.state.encounters import ENEMY_ARCHETYPES
from dd_simulator.state.item_catalog import RARITIES, catalog_items
from dd_simulator.state.seed import seed_demo_campaign
from dd_simulator.ui.item_icons import ASSET_ROOT, LIBRARY_ROOT, icon_path, icon_records, resolve_icon


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
