"""Build `ui/assets/icons/item_icon_manifest.json` from the item catalog and icon library.

Each catalog record (`item_manifest.json`) goes to a pool of library icons chosen by name
keyword, then by category and subtype. Within a pool, icons are ordered by detail (the
byte size of the 128 px PNG, a proxy for how ornate a painting is) and records are
ordered by visual tier, so records spread across the pool and higher tiers get the more
detailed art. Re-running with the same inputs produces the same manifest.

Usage: python scripts/build_item_icon_manifest.py [PROJECT_RESOURCES_ASSETS_ROOT]
"""

from __future__ import annotations

from collections import defaultdict
import json
import re
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from import_codex_assets import _downscaled_png
from import_item_icons import DEFAULT_SOURCE_ROOT, ICON_ROOT, ICON_SIZE, MANIFEST_PATH


CATALOG_PATH = ICON_ROOT / "item_manifest.json"

# Name keywords for subtypes whose records differ in kind (first match wins).
KEYWORD_POOLS = (
    (r"fang|claw|horn", "items/claw-loot"),
    (r"feather", "items/wing"),
    (r"skull|bone", "items/bones"),
    (r"herb|flower|blossom|leaf|sprig|pinecone|seed", "items/flower"),
    (r"silk", "items/spider-loot"),
    (r"slime|eye|heart|essence|gem|shard", "items/monster-loot"),
    (r"hide|leather|cloth|twine", "items/hunting-trophy"),
    (r"parchment", "items/book"),
    (r"coral", "items/sea"),
    (r"bomb", "items/battle-loot"),
)
KEYWORD_SUBTYPES = {"monster_part", "elixir"}
SUBTYPE_POOLS = {
    "shortsword": "items/weapons/sword", "longsword": "items/weapons/sword",
    "dagger": "items/weapons/daggers",
    "axe": "items/weapons/axe", "battleaxe": "items/weapons/axe",
    "greataxe": "items/weapons/axe", "hatchet": "items/weapons/axe",
    "bow": "items/weapons/bow-and-crossbow", "crossbow": "items/weapons/bow-and-crossbow",
    "arrow": "items/hunting",
    "mace": "items/weapons/crushing-weapon", "hammer": "items/weapons/crushing-weapon",
    "warhammer": "items/weapons/crushing-weapon",
    "battlehammer": "items/weapons/crushing-weapon",
    "spear": "items/weapons/lance", "staff": "items/weapons/staff",
    "scepter": "items/weapons/staff", "scythe": "items/weapons/different-weapon",
    "chestpiece": "items/armor/armor", "cloak": "items/armor/armor",
    "belt": "items/armor/belt", "boots": "items/armor/boot",
    "gloves": "items/armor/glove", "helmet": "items/armor/helmet",
    "shield": "items/armor/shields",
    "ring": "items/jewelry", "amulet": "items/jewelry", "medallion": "items/jewelry",
    "elixir": "items/elixir", "alchemy": "items/liquid",
    "fruit": "items/fruit", "vegetable": "items/vegetable", "mushroom": "items/mushroom",
    "prepared": "items/medieval-food", "drink": "items/medieval-food",
    "ingredient": "items/cooking-ingredient", "seafood": "items/sea",
    "coin": "items/treasure-and-chest", "nugget": "items/mining",
    "key": "items/treasure-and-chest", "chest": "items/treasure-and-chest",
    "crate": "items/treasure-and-chest", "pouch": "items/treasure-and-chest",
    "sack": "items/treasure-and-chest", "goblet": "items/treasure-and-chest",
    "rune": "items/magical-artifact",
    "ore": "items/mining", "ingot": "items/mining", "gem": "items/mining",
    "pickaxe": "items/mining", "chisel": "items/mining", "whetstone": "items/mining",
    "shovel": "items/farming", "bucket": "items/farming",
    "book": "items/book", "journal": "items/book", "letter": "items/book",
    "map": "items/book", "scroll": "items/book", "tome": "items/book",
    "berserker": "skills/berserker", "melee": "skills/swordsman",
    "paladin": "skills/paladin", "ranger": "skills/forest-elf/RPG-Forest-Elf-Skill-Icons", "status": "skills/buff",
    "arcane": "skills/illusionist", "blood": "skills/blood-mage",
    "earth": "skills/earth-magician", "fire": "skills/pyromancer", "holy": "skills/priest",
    "ice": "skills/cryomancer", "water": "skills/cryomancer",
    "lightning": "skills/lightning-mage", "nature": "skills/druid",
    "necromancy": "skills/undead", "poison": "skills/debuff",
}
DEFAULT_POOL = "items/misc"


def pack_icons(source_root: Path, pool: str) -> list[Path]:
    """Return the transparent PNGs of the first pack under `pool`, by numeric name."""

    pngs = sorted(path for path in (source_root / pool).rglob("*.png") if path.stem.isdigit())
    transparent = [path for path in pngs if "without" in path.parent.name.casefold()]
    chosen = transparent or [path for path in pngs if path.parent.name == "PNG"]
    if not chosen:
        raise SystemExit(f"No icons under {source_root / pool}")
    folder = chosen[0].parent
    return sorted((path for path in chosen if path.parent == folder), key=lambda p: int(p.stem))


def packaged_name(relative: Path) -> str:
    parts = relative.parts
    theme = parts[1] if parts[0] == "items" and parts[1] not in {"weapons", "armor"} else parts[2]
    prefix = "skill-" if parts[0] == "skills" else ""
    return f"{prefix}{theme}-{relative.stem}.png"


def pool_for(record: dict[str, object]) -> str:
    subtype = str(record["subtype"])
    if subtype in KEYWORD_SUBTYPES:
        name = str(record["semantic_name"]).casefold()
        for pattern, pool in KEYWORD_POOLS:
            if re.search(pattern, name):
                return pool
    return SUBTYPE_POOLS.get(subtype, DEFAULT_POOL)


def main(argv: list[str]) -> int:
    source_root = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE_ROOT
    QGuiApplication.instance() or QGuiApplication([])
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in catalog:
        groups[pool_for(record)].append(record)

    sources: dict[str, str] = {}
    records: dict[str, str] = {}
    for pool, members in sorted(groups.items()):
        icons = sorted(
            pack_icons(source_root, pool),
            key=lambda path: (len(_downscaled_png(path, ICON_SIZE)), int(path.stem)),
        )
        members.sort(key=lambda record: (int(record["visual_tier"]), int(record["index"])))
        for rank, record in enumerate(members):
            icon = icons[rank * len(icons) // len(members)]
            relative = icon.relative_to(source_root)
            name = packaged_name(relative)
            sources[name] = relative.as_posix()
            records[str(record["index"])] = name
    manifest = {
        "sources": dict(sorted(sources.items())),
        "records": dict(sorted(records.items(), key=lambda item: int(item[0]))),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(records)} records mapped to {len(sources)} icons.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
