"""Deterministic semantic item icons from the packaged CraftPix icon library."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

from PySide6.QtCore import QVariantAnimation, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QLabel


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
    apply_rarity_glow(label, rarity)
    if pixmap.isNull():
        label.hide()
    elif label.parentWidget() is not None:
        label.show()


@lru_cache(maxsize=4)
def _rarity_colours(theme_id: str) -> dict[str, str]:
    path = Path(__file__).resolve().parent / "themes" / theme_id / "theme.json"
    try:
        codex = json.loads(path.read_text(encoding="utf-8"))["tokens"]["codex"]
    except (OSError, KeyError, json.JSONDecodeError):
        return {}
    return {key.removeprefix("rarity_"): value for key, value in codex.items() if key.startswith("rarity_")}


class _RarityGlow(QGraphicsDropShadowEffect):
    def __init__(self, parent) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.base = QColor()
        _GLOWS.append(self)

    def set_base(self, colour: QColor) -> None:
        self.base = colour
        self.set_strength(_pulse_strength)

    def set_strength(self, strength: float) -> None:
        colour = QColor(self.base)
        colour.setAlphaF(strength)
        self.setColor(colour)

    def draw(self, painter) -> None:  # type: ignore[no-untyped-def]
        # A near-full-opacity pass first, then the full pass: the glow is about twice
        # as strong and the item itself is drawn last, on top, untinted.
        painter.save()
        painter.setOpacity(0.95)
        super().draw(painter)
        painter.restore()
        super().draw(painter)


# ponytail: plain list pruned on each pulse tick; a weak set if icons churn heavily
_GLOWS: list[_RarityGlow] = []
_pulse: QVariantAnimation | None = None
_pulse_strength = 1.0


def _apply_pulse(phase: object) -> None:
    global _pulse_strength
    # a light breath between 60% and full strength
    _pulse_strength = 0.8 + 0.2 * math.cos(2 * math.pi * float(phase))
    for glow in list(_GLOWS):
        try:
            glow.set_strength(_pulse_strength)
        except RuntimeError:  # its icon was deleted
            _GLOWS.remove(glow)


def set_rarity_glow_pulse(enabled: bool) -> None:
    """Start or stop the shared, slow pulse of every rarity glow."""

    global _pulse
    if not enabled:
        if _pulse is not None:
            _pulse.stop()
            _pulse = None
        _apply_pulse(0.0)
        return
    if _pulse is None:
        _pulse = QVariantAnimation(QApplication.instance())
        _pulse.setStartValue(0.0)
        _pulse.setEndValue(1.0)
        _pulse.setDuration(2400)
        _pulse.setLoopCount(-1)
        _pulse.valueChanged.connect(_apply_pulse)
        _pulse.start()


def rarity_glow_pulsing() -> bool:
    return _pulse is not None


def apply_rarity_glow(icon: QLabel, rarity: str) -> None:
    """Glow outline in the rarity colour around the icon's shape; none for common items."""

    application = QApplication.instance()
    theme_id = str(application.property("themeId") or "high_fantasy") if application else "high_fantasy"
    colour = _rarity_colours(theme_id).get(rarity.casefold())
    if not colour or rarity.casefold() == "common":
        icon.setGraphicsEffect(None)
        return
    glow = icon.graphicsEffect()
    if not isinstance(glow, _RarityGlow):
        glow = _RarityGlow(icon)
        glow.setOffset(0, 0)
        icon.setGraphicsEffect(glow)
    # 65 px blur at the 59 px inventory icon; never under 45 px on small icons
    glow.setBlurRadius(max(45, icon.width() * 65 // 59))
    glow.set_base(QColor(colour))


def ui_icon(name: str) -> QIcon:
    return QIcon()
