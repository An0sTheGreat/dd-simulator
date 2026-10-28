"""Deterministic semantic item icons from the packaged CraftPix icon library."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QLabel


ASSET_ROOT = Path(__file__).parent / "assets" / "icons"
LIBRARY_ROOT = ASSET_ROOT / "library"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
RARITY_TIER = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
}
ALIASES = {
    "ammunition": "weapon arrow ranged",
    "bandage": "potion healing cloth consumable",
    "charm": "magic item amulet",
    "coat": "armor chestpiece cloak",
    "flint": "tool fire kindling",
    "health": "potion healing red",
    "lockpick": "key tool unlock",
    "moonstone": "material gem magic",
    "ration": "food prepared travel",
}
EXACT_ICON_INDEX = {
    "arrows": 444,
    "bandages": 1156,
    "field bandages": 1156,
    "greater healing potion": 918,
    "health potion": 919,
    "healing potion": 919,
    "minor healing vial": 920,
    "restorative draught": 919,
    # Preset quest rewards carry no category, so name them here (The Last Orrery of Sol).
    "gravline bracer": 756,
    "jovian aegis": 601,
    "lunar lens": 1199,
    "map of roads not taken": 1184,
    "martian vector": 1177,
    "meridian harness earth state": 760,
    "meridian harness solar state": 745,
    "nullglass edge": 334,
    "orrery key": 1194,
    "pelagic ampoule": 929,
    "starlight injector": 941,
    "stormsilk mantle": 817,
    "vector splitter": 1085,
}
SKILL_ICON_INDEX = {
    "attack": 1612,
    "strength": 1614,
    "defense": 1625,
    "ranged": 1596,
    "survival": 1601,
    "magic": 1241,
    "herblore": 1240,
    "crafting": 1099,
    "warden s mark": 1591,
    "quick shot": 1608,
    "field dressing": 1674,
    "shield wall": 1631,
}
COMMON_ITEM_ICON_INDEX = {
    "cloth": 1156,
    "flint steel": 1221,
    "gold": 1215,
    "greystone charm": 822,
    "healer s kit": 1172,
    "herbs": 1168,
    "iron dagger": 320,
    "iron scraps": 1062,
    "leather gloves": 754,
    "lockpick": 1192,
    "map fragment": 1184,
    "merchant letter": 1191,
    "moonstone": 1088,
    "oak shield": 610,
    "rope": 1210,
    "trail boots": 784,
    "travel rations": 1001,
    "warden coat": 719,
    "water flask": 1012,
}


@dataclass(frozen=True, slots=True)
class IconRecord:
    index: int
    semantic_name: str
    category: str
    subtype: str
    tags: str
    visual_tier: int


def _tokens(value: str) -> frozenset[str]:
    return frozenset(TOKEN_PATTERN.findall(value.casefold()))


@lru_cache(maxsize=1)
def icon_records() -> tuple[IconRecord, ...]:
    raw = json.loads((ASSET_ROOT / "item_manifest.json").read_text(encoding="utf-8"))
    return tuple(
        IconRecord(
            index=int(value["index"]),
            semantic_name=str(value["semantic_name"]),
            category=str(value["category"]).casefold(),
            subtype=str(value["subtype"]).casefold(),
            tags=str(value["tags"]).casefold(),
            visual_tier=int(value["visual_tier"]),
        )
        for value in raw
    )


@lru_cache(maxsize=4096)
def resolve_icon(
    name: str,
    rarity: str = "common",
    category: str = "misc",
    context: str = "",
) -> IconRecord | None:
    """Resolve one stable atlas record from generated item semantics."""

    normalized_name = " ".join(TOKEN_PATTERN.findall(name.casefold()))
    if not normalized_name:
        return None
    target_tier = RARITY_TIER.get(rarity.casefold(), 0)
    fixed_index = EXACT_ICON_INDEX.get(normalized_name)
    if category.casefold().strip() in {"skill", "spell"}:
        fixed_index = SKILL_ICON_INDEX.get(normalized_name, fixed_index)
    elif target_tier == 0:
        fixed_index = COMMON_ITEM_ICON_INDEX.get(normalized_name, fixed_index)
    if fixed_index is not None:
        return next(
            (record for record in icon_records() if record.index == fixed_index),
            None,
        )
    expanded = " ".join(
        ALIASES[token]
        for token in _tokens(f"{name} {category} {context}")
        if token in ALIASES
    )
    query = _tokens(f"{name} {category} {context} {expanded}")
    category_token = category.casefold().strip()

    exact = [
        record
        for record in icon_records()
        if " ".join(TOKEN_PATTERN.findall(record.semantic_name.casefold()))
        == normalized_name
    ]
    if exact:
        return min(
            exact,
            key=lambda record: (abs(record.visual_tier - target_tier), record.index),
        )

    def rank(record: IconRecord) -> tuple[int, int, int]:
        record_name = " ".join(TOKEN_PATTERN.findall(record.semantic_name.casefold()))
        record_tokens = _tokens(
            f"{record.semantic_name} {record.category} {record.subtype} {record.tags}"
        )
        overlap = len(query & record_tokens)
        score = overlap * 12
        tier_distance = abs(record.visual_tier - target_tier)
        if record_name == normalized_name:
            score += max(0, 70 - tier_distance * 35)
        elif normalized_name in record_name or record_name in normalized_name:
            score += max(0, 25 - tier_distance * 10)
        if record.subtype in query:
            score += 35
        if record.category == category_token:
            score += 28
        if record.category in query:
            score += 18
        score += 40 - tier_distance * 15
        tie = int.from_bytes(
            hashlib.sha256(f"{normalized_name}:{record.index}".encode()).digest()[:4],
            "big",
        )
        return score, -tier_distance, -tie

    return max(icon_records(), key=rank, default=None)


@lru_cache(maxsize=1)
def _library_icons() -> dict[str, str]:
    raw = json.loads((ASSET_ROOT / "item_icon_manifest.json").read_text(encoding="utf-8"))
    return raw["records"]


def icon_path(record: IconRecord) -> Path:
    """Return the packaged library painting mapped to a catalog record."""

    return LIBRARY_ROOT / _library_icons()[str(record.index)]


@lru_cache(maxsize=4096)
def _record_pixmap(index: int, size: int) -> QPixmap:
    pixmap = QPixmap(str(LIBRARY_ROOT / _library_icons().get(str(index), "")))
    if pixmap.isNull():
        return QPixmap()
    return pixmap.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def item_icon_pixmap(
    name: str,
    *,
    rarity: str = "common",
    category: str = "misc",
    context: str = "",
    size: int = 32,
    force: bool = False,
) -> QPixmap:
    record = resolve_icon(name, rarity, category, context)
    return QPixmap() if record is None else _record_pixmap(record.index, size)


class SemanticIconLabel(QLabel):
    def __init__(
        self,
        name: str,
        *,
        rarity: str,
        category: str,
        context: str,
        size: int,
        object_name: str,
    ) -> None:
        super().__init__()
        self.icon_name = name
        self.icon_rarity = rarity
        self.icon_category = category
        self.icon_context = context
        self.setObjectName(object_name)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName(f"{name} icon")
        self.refresh_theme_icon()

    def refresh_theme_icon(self) -> None:
        refresh_item_icon(
            self,
            self.icon_name,
            rarity=self.icon_rarity,
            category=self.icon_category,
            context=self.icon_context,
        )


def item_icon_label(
    name: str,
    *,
    rarity: str = "common",
    category: str = "misc",
    context: str = "",
    size: int = 32,
    object_name: str = "itemIcon",
) -> SemanticIconLabel:
    return SemanticIconLabel(
        name,
        rarity=rarity,
        category=category,
        context=context,
        size=size,
        object_name=object_name,
    )


def refresh_item_icon(
    label: QLabel,
    name: str,
    *,
    rarity: str = "common",
    category: str = "misc",
    context: str = "",
) -> None:
    pixmap = item_icon_pixmap(
        name,
        rarity=rarity,
        category=category,
        context=context,
        size=max(1, label.width()),
    )
    label.setPixmap(pixmap)
    if pixmap.isNull():
        label.hide()
    elif label.parentWidget() is not None:
        label.show()


def ui_icon(name: str) -> QIcon:
    return QIcon()
