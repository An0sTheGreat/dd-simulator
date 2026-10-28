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

from import_codex_assets import _downscaled_png
from import_item_icons import DEFAULT_SOURCE_ROOT, ICON_ROOT, ICON_SIZE, MANIFEST_PATH


CATALOG_PATH = ICON_ROOT / "item_manifest.json"

# A pool names one or more packs joined by "+"; "#" picks icon numbers in a pack, so a
# pack that mixes kinds (bows and crossbows, maces and hammers) feeds each subtype only
# the icons that show it. The numbers were chosen by viewing contact sheets of each pack.
ELIXIR_COLOURS = (
    (r"bomb", "items/pirate#38+items/goblin#23+items/mining#18+items/pirated#39"),
    (r"empty", "items/pirate#17+items/pirated#47"),
    (r"stew", "items/medieval-food#30-32"),
    (r"blue|mana|frost|freez|tidal|clarity|water", "items/elixir#3,6,10,19,21,25,33,35,39,50"),
    (r"heal|blood|crimson|heart|rejuv|berserk|love|cherry|berry|rose|red",
     "items/elixir#2,14,15,18,23,31,32,46"),
    (r"shadow|void|arcane|dream|violet|night|fairy|winged", "items/elixir#5,27,29,36,37,41,49"),
    (r"antidote|herb|stamina|venom|leaf|mint|mushroom|green|root|earthen",
     "items/elixir#9,11,20,22,26,38,47"),
    (r"amber|gold|sun|citrus|honey|peach|star|nectar", "items/elixir#1,8,16,24,30,34,45,48"),
)
# Name keywords for subtypes whose records differ in kind (first match wins).
KEYWORD_POOLS = {
    "elixir": ELIXIR_COLOURS, "alchemy": ELIXIR_COLOURS,
    "ore": (
        (r"gold", "items/mining#30,33"), (r"amethyst", "items/mining#27"),
        (r"sapphire|mithril", "items/mining#26,28"), (r"copper", "items/mining#29,37"),
        (r"coal|dark|black", "items/mining#32"), (r"silver|iron", "items/mining#31"),
        (r"ruby|fire|flame", "items/mining#38,39"),
    ),
    "ingot": (
        (r"gold", "items/dwarf#28+items/kobold#37"),
        (r"copper|bronze|meteor|ruby", "items/mining#35"),
    ),
}
SCROLLS = ("items/high-quality-loot#20,30,44+items/fantasy-loot#8,37,49"
           "+items/battle-loot#44,45+items/boss-loot#43,44")
HAMMERS = "items/weapons/crushing-weapon#34,37-50"
SUBTYPE_POOLS = {
    "shortsword": "items/weapons/sword", "longsword": "items/weapons/sword",
    "dagger": "items/weapons/daggers#1-10,13-17,19-50",
    "axe": "items/weapons/axe", "battleaxe": "items/weapons/axe",
    "greataxe": "items/weapons/axe", "hatchet": "items/weapons/axe#4-6,8-14,16,17,19,20",
    "bow": "items/weapons/bow-and-crossbow#1-25",
    "crossbow": "items/weapons/bow-and-crossbow#26-50",
    "arrow": "skills/archer#1,2,4,5,8,10,15,17,31,40,43,50",
    "mace": "items/weapons/crushing-weapon#1-33,35,36",
    "hammer": HAMMERS, "warhammer": HAMMERS, "battlehammer": HAMMERS,
    "spear": "items/weapons/lance", "staff": "items/weapons/staff",
    "scepter": "items/weapons/staff",
    "scythe": "items/weapons/different-weapon#26,29,30,44,47",
    "chestpiece": "items/armor/armor#1-6,9-31,33,34,36-40,42-47,49,50",
    "cloak": "items/armor/armor#7,8,32,35,41,48",
    "belt": "items/armor/belt", "boots": "items/armor/boot",
    "gloves": "items/armor/glove", "helmet": "items/armor/helmet",
    "shield": "items/armor/shields",
    "ring": "items/jewelry#1-16", "amulet": "items/jewelry#17-33",
    "medallion": "items/jewelry#17-33",
    "elixir": "items/elixir", "alchemy": "items/elixir",
    "key": "items/treasure-and-chest#25-36,42,43",
    "chest": "items/treasure-and-chest#1-24,37-41,44",
    "crate": "items/treasure-and-chest#1-24,37-41,44",
    "rune": "items/goblin#18,20+items/kobold#27+items/misc#31+items/magical-artifact#39",
    "ore": "items/mining#26-33,37-39",
    "ingot": "items/mining#36+items/dwarf#9",
    "book": "items/book", "journal": "items/book", "tome": "items/book", "scroll": SCROLLS,
    "berserker": "skills/berserker", "melee": "skills/swordsman",
    "paladin": "skills/paladin", "ranger": "skills/forest-elf/RPG-Forest-Elf-Skill-Icons",
    "status": "skills/buff", "arcane": "skills/illusionist", "blood": "skills/blood-mage",
    "earth": "skills/earth-magician", "fire": "skills/pyromancer", "holy": "skills/priest",
    "ice": "skills/cryomancer", "water": "items/liquid#2,3,5,11-13,25,29,33,37-41,48",
    "lightning": "skills/lightning-mage", "nature": "skills/druid",
    "necromancy": "skills/undead", "poison": "skills/debuff",
}
DEFAULT_POOL = "items/misc"
# Records whose names call for one specific painting ("pack#number").
NAME_ICONS = {
    # food
    "Lemon": "items/fruit#8", "Peach": "items/fruit#15", "Pear": "items/fruit#7",
    "Red Apple": "items/fruit#1", "Golden Apple": "items/fruit#50",
    "Eggplant": "items/vegetable#8", "Strawberry": "items/berry#12",
    "Tomato": "items/vegetable#7", "Whole Melon": "items/berry#10",
    "Watermelon Slice": "items/berry#1", "Orange": "items/fruit#6",
    "Starfruit": "items/fruit#28", "Chestnut": "items/fruit#34", "Cherries": "items/berry#9",
    "Banana": "items/fruit#3", "Banana Bunch": "items/fruit#3",
    "Blueberries": "items/berry#8", "Garlic Bulb": "items/vegetable#28",
    "Pineapple": "items/fruit#5", "Purple Grapes": "items/berry#22",
    "Sunflower": "items/farming#50",
    "Carrot": "items/vegetable#11", "Potato": "items/vegetable#6",
    "Pumpkin": "items/vegetable#1", "Ear of Corn": "items/vegetable#23",
    "Turnip": "items/vegetable#38", "Radish": "items/vegetable#4",
    "Beetroot": "items/vegetable#5", "Red Onion": "items/vegetable#17",
    "Green Cabbage": "items/vegetable#14", "Leek": "items/vegetable#29",
    "Cauliflower": "items/vegetable#12", "Russet Potato": "items/vegetable#47",
    "Chili Pepper": "items/vegetable#32",
    "Milk Bottle": "items/liquid#49", "Jam Jar": "items/liquid#44",
    "Yogurt Cup": "items/cooking-ingredient#34", "Honey Jar": "items/liquid#50",
    "Water Jar": "items/liquid#17", "Water Bottle": "items/liquid#31",
    "Cooking Oil": "items/liquid#21", "Red Wine Bottle": "items/dwarf#32",
    "Tea Kettle": "items/liquid#43", "Beer Mug": "items/medieval-food#6",
    "Bread Roll": "items/medieval-food#12", "Bread Loaf": "items/pirate#32",
    "Berry Tart": "items/medieval-food#25", "Cheese Wedge": "items/cooking-ingredient#15",
    "Brown Egg": "items/cooking-ingredient#37", "White Egg": "items/cooking-ingredient#37",
    "Fried Egg": "items/medieval-food#24",
    "Flame Essence": "items/liquid#42", "Honey Dipper": "items/cooking-ingredient#33",
    "Honeycomb": "items/sea#37", "Honey Cluster": "items/liquid#50",
    "Flour Sack": "items/farming#29", "Sugar Cubes": "items/cooking-ingredient#39",
    "Salt Pile": "items/cooking-ingredient#24", "Rice Bowl": "items/medieval-food#15",
    "Spice Jar": "items/cooking-ingredient#23", "Seasoning Jar": "items/cooking-ingredient#31",
    "Ham": "items/medieval-food#26", "Raw Steak": "items/hunting#20",
    "Cooked Steak": "items/medieval-food#28", "Marbled Meat": "items/cooking-ingredient#43",
    "Cooked Drumstick": "items/high-quality-loot#18", "Grilled Meat": "items/medieval-food#5",
    "Raw Drumstick": "items/cooking-ingredient#50",
    "Roasted Drumstick": "items/medieval-food#19", "Roasted Wing": "items/medieval-food#34",
    "Blue Minnow": "items/sea#34", "Silver Minnow": "items/sea#34",
    "Azure Fish": "items/sea#34", "Green River Fish": "items/sea#34",
    "Golden Fish": "items/pirate#35", "Sunfish": "items/sea#33",
    "Orange Octopus": "items/sea#21", "Frozen Fish": "items/sea#50",
    "River Shrimp": "items/hunting#3", "Fish Skeleton": "items/sea#16",
    "Swordfish": "items/sea#31", "Starfish": "items/sea#19",
    "Seafood Stew": "items/medieval-food#49", "Crab Claw": "items/sea#45",
    "Green Eel": "items/hunting#50", "Pink Shrimp": "items/hunting#3",
    "Red Lobster": "items/sea#45",
    "Brown Mushroom": "items/alchemical-ingredient#29",
    "Spotted Mushroom": "items/alchemical-ingredient#27",
    "Red Mushroom": "items/alchemical-ingredient#28",
    "Mushroom Bundle": "items/alchemical-ingredient#30",
    # treasure and materials
    "Pearl": "items/sea#10", "Ruby Crystal": "items/mining#41",
    "Emerald Gem": "items/mining#40", "Diamond": "items/mining#45",
    "Sapphire Shard": "items/mining#49", "Sapphire Cluster": "items/mining#46",
    "Amber Gem": "items/mining#23", "Gold Nuggets": "items/mining#30",
    "Copper Coin": "items/misc#22", "Gold Coin": "items/treasure-and-chest#46",
    "Large Gold Coin": "items/pirated#31", "Gold Stack": "items/treasure-and-chest#45",
    "Gold Pile": "items/pirate#12", "Small Gold Pile": "items/battle-loot#33",
    "Brass Key": "items/treasure-and-chest#29", "Ruby Key": "items/treasure-and-chest#42",
    "Gold Key": "items/treasure-and-chest#26", "Bronze Key": "items/treasure-and-chest#31",
    "Silver Key": "items/treasure-and-chest#25", "Steel Key": "items/treasure-and-chest#33",
    "Supply Chest": "items/treasure-and-chest#1", "Locked Chest": "items/treasure-and-chest#3",
    "Small Treasure Chest": "items/treasure-and-chest#2",
    "Locked Crate": "items/farming#45", "Supply Crate": "items/high-quality-loot#40",
    "Wooden Barrel": "items/farming#43", "Water Barrel": "items/liquid#18",
    "Golden Goblet": "items/treasure-and-chest#48", "Silver Goblet": "items/battle-loot#34",
    "Wooden Mug": "items/pirated#49", "Metal Tankard": "items/dwarf#31",
    "Clay Pot": "items/fantasy-loot#15", "Clay Bowl": "items/farming#40",
    "Water Basin": "items/liquid#29", "Small Pouch": "items/misc#32",
    "Coin Pouch": "items/misc#37", "Large Sack": "items/farming#26",
    "Burning Campfire": "items/goblin#33", "Campfire": "items/goblin#33",
    "Cold Campfire": "items/dwarf#35", "Cooking Fire": "items/liquid#23",
    "Iron Gear": "items/high-quality-loot#39", "Kindling": "items/high-quality-loot#38",
    "Coiled Rope": "items/pirate#13",
    "Black Bomb": "items/pirate#38", "Lit Bomb": "items/pirated#39",
    # quest items
    "Open Ledger": "items/book#33", "Brown Journal": "items/book#46",
    "Leather Journal": "items/dwarf#13", "Letter": "items/fantasy-loot#8",
    "Sealed Letter": "items/pirate#14", "Treasure Map": "items/pirated#18",
    "Compass Medallion": "items/pirated#19", "Quest Scroll": "items/high-quality-loot#20",
    "Sealed Scroll": "items/pirate#1", "Royal Decree": "items/fantasy-loot#49",
    "Blank Scroll": "items/boss-loot#43", "Blank Parchment": "items/fantasy-loot#37",
    # tools
    "Metal Bucket": "items/farming#41", "Wooden Bucket": "items/farming#42",
    "Candle": "items/battle-loot#1", "Wax Candle": "items/kobold#46",
    "Iron Cauldron": "items/goblin#39", "Metal Chisel": "items/farming#6",
    "Compass": "items/pirated#20", "Smithing Hammer": "items/dwarf#21",
    "Cooking Ladle": "items/kobold#33", "Cooking Pan": "items/kobold#33",
    "Hooded Lantern": "items/mining#14", "Iron Lantern": "items/dwarf#27",
    "Magnifying Glass": "items/fantasy-loot#17", "Wooden Mallet": "items/mining#13",
    "Mortar Bowl": "items/cooking-ingredient#28", "Mining Pickaxe": "items/mining#1",
    "Harvest Scythe": "items/farming#3", "Shovel": "items/mining#5",
    "Torch": "items/goblin#33", "Whetstone": "items/dwarf#9",
    "Hourglass": "items/pirate#17",  # no hourglass painting in the library
    # monster parts
    "Ancient Parchment": "items/fantasy-loot#37",
    "Beast Seeds": "items/alchemical-ingredient#46",
    "Blood Shard": "items/fantasy-loot#2", "Blue Flower": "items/alchemical-ingredient#31",
    "Bone Fragments": "items/bones#11", "Long Bone": "items/hunting#13",
    "Bottled Slime": "items/misc#13", "Broad Leaf": "items/high-quality-loot#19",
    "Broken Skull": "items/fantasy-loot#9", "Crescent Fang": "items/hunting#12",
    "Crimson Heart": "items/misc#41", "Curved Horn": "items/hunting#14",
    "Cut Log": "items/dwarf#35", "Fish Bones": "items/hunting#24",
    "Green Herbs": "items/goblin#36", "Herb Sprig": "items/misc#11",
    "Horned Skull": "items/alchemical-ingredient#7", "Human Skull": "items/kobold#32",
    "Ivory Fang": "items/boss-loot#24", "Leather Scrap": "items/hunting#19",
    "Monster Eye": "items/misc#28", "Pale Blossom": "items/alchemical-ingredient#33",
    "Parchment Scrap": "items/dwarf#5", "Pinecone": "items/fruit#30",
    "Pink Coral": "items/sea#25", "Pink Essence": "items/misc#38",
    "Raven Feather": "items/wing#16", "Slime Chunks": "items/liquid#4",
    "Slime Orb": "items/alchemical-ingredient#21", "Slime Puddle": "items/liquid#14",
    "Spider Silk": "items/fantasy-loot#45", "Tanned Hide": "items/hunting#17",
    "Torn Cloth": "items/kobold#16", "Twig Bundle": "items/cooking-ingredient#38",
    "Twine Coil": "items/fantasy-loot#44", "Void Gem": "items/battle-loot#9",
    "White Feather": "items/wing#4", "White Flower": "items/high-quality-loot#11",
    "Witch Hat": "items/halloween#34", "Wooden Doll": "items/misc#47",
    "Wooden Stick": "items/cooking-ingredient#38",
}


def _icon_number(path: Path) -> int | None:
    match = re.search(r"(\d+)$", path.stem)
    return int(match.group(1)) if match else None


def _pack(source_root: Path, pack: str) -> dict[int, Path]:
    """Return the transparent PNGs of the first pack under `pack`, by icon number."""

    pngs = sorted(path for path in (source_root / pack).rglob("*.png") if _icon_number(path))
    transparent = [path for path in pngs if "without" in path.parent.name.casefold()]
    chosen = transparent or [path for path in pngs if path.parent.name == "PNG"]
    if not chosen:
        raise SystemExit(f"No icons under {source_root / pack}")
    folder = chosen[0].parent
    return {_icon_number(path): path for path in chosen if path.parent == folder}


def _numbers(spec: str) -> list[int]:
    numbers: list[int] = []
    for part in spec.split(","):
        first, _, last = part.partition("-")
        numbers.extend(range(int(first), int(last or first) + 1))
    return numbers


def pack_icons(source_root: Path, pool: str) -> list[Path]:
    """Return the icons a pool names: packs joined by "+", "#" picks icon numbers."""

    icons: list[Path] = []
    for part in pool.split("+"):
        pack, _, spec = part.partition("#")
        found = _pack(source_root, pack)
        icons.extend(found[number] for number in (_numbers(spec) if spec else sorted(found)))
    return icons


def packaged_name(relative: Path) -> str:
    parts = relative.parts
    theme = parts[2] if parts[0] == "items" and parts[1] in {"weapons", "armor"} else parts[1]
    prefix = "skill-" if parts[0] == "skills" else ""
    return f"{prefix}{theme}-{_icon_number(relative)}.png"


def pool_for(record: dict[str, object]) -> str:
    name = str(record["semantic_name"])
    if name in NAME_ICONS:
        return NAME_ICONS[name]
    subtype = str(record["subtype"])
    for pattern, pool in KEYWORD_POOLS.get(subtype, ()):
        if re.search(pattern, name.casefold()):
            return pool
    return SUBTYPE_POOLS.get(subtype, DEFAULT_POOL)


def main(argv: list[str]) -> int:
    source_root = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE_ROOT
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in catalog:
        groups[pool_for(record)].append(record)

    sources: dict[str, str] = {}
    records: dict[str, str] = {}
    for pool, members in sorted(groups.items()):
        icons = sorted(
            pack_icons(source_root, pool),
            key=lambda path: (len(_downscaled_png(path, ICON_SIZE)), _icon_number(path)),
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
