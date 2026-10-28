"""Semantic item catalog and deterministic tier-weighted loot selection."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import random
import sqlite3


MANIFEST_PATH = (
    Path(__file__).parent.parent / "ui" / "assets" / "icons" / "item_manifest.json"
)
RARITIES = ("common", "uncommon", "rare", "epic", "legendary")
TIER_WEIGHTS = (100.0, 35.0, 12.0, 4.0, 1.0)


@dataclass(frozen=True, slots=True)
class CatalogItem:
    id: str
    icon_index: int
    name: str
    category: str
    subtype: str
    tags: tuple[str, ...]
    tier: int

    @property
    def rarity(self) -> str:
        return RARITIES[self.tier]

    @property
    def description(self) -> str:
        role = self.subtype.replace("_", " ") or self.category.replace("_", " ")
        return f"{self.name}, a {self.rarity} {role} suited to a fantasy adventure."


@lru_cache(maxsize=1)
def catalog_items() -> tuple[CatalogItem, ...]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return tuple(
        CatalogItem(
            id=f"catalog-{int(value['index']):04d}",
            icon_index=int(value["index"]),
            name=str(value["semantic_name"]),
            category=str(value["category"]).casefold(),
            subtype=str(value["subtype"]).casefold(),
            tags=tuple(
                token for token in str(value["tags"]).casefold().split("|") if token
            ),
            tier=max(0, min(4, int(value["visual_tier"]))),
        )
        for value in raw
    )


@lru_cache(maxsize=4096)
def catalog_item(identity: str) -> CatalogItem | None:
    normalized = " ".join(identity.casefold().split())
    return next(
        (
            item
            for item in catalog_items()
            if item.id == normalized or " ".join(item.name.casefold().split()) == normalized
        ),
        None,
    )


def select_loot(seed: str, *, count: int = 1) -> tuple[CatalogItem, ...]:
    """Select unique items; every catalog record retains non-zero probability."""

    rng = random.Random(
        int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big")
    )
    pool = list(catalog_items())
    selected: list[CatalogItem] = []
    for _ in range(min(max(0, count), len(pool))):
        chosen = rng.choices(pool, weights=[TIER_WEIGHTS[item.tier] for item in pool])[0]
        selected.append(chosen)
        pool.remove(chosen)
    return tuple(selected)


def loot_shortlist(seed: str, *, count: int = 8) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "subtype": item.subtype,
            "tags": item.tags[:3],
            "tier": item.tier,
            "rarity": item.rarity,
        }
        for item in select_loot(seed, count=count)
    )


def ensure_catalog_merchant_stock(connection: sqlite3.Connection) -> None:
    """Give each existing merchant a small stable sample from the full catalog."""

    merchant_ids = [
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT npc_id FROM merchant_stock ORDER BY npc_id"
        )
    ]
    for npc_id in merchant_ids:
        start = int(
            connection.execute(
                "SELECT COALESCE(MAX(display_order), -1) + 1 FROM merchant_stock WHERE npc_id = ?",
                (npc_id,),
            ).fetchone()[0]
        )
        for offset, item in enumerate(select_loot(f"merchant:{npc_id}", count=6)):
            durable = item.category in {"armor", "weapon", "tool", "magic_item"}
            connection.execute(
                "INSERT OR IGNORE INTO merchant_stock("
                "id, npc_id, name, quantity, rarity, durability, maximum_durability, "
                "base_value, description, display_order"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"stock-{npc_id}-{item.id}", npc_id, item.name,
                    1 if item.tier > 1 else 2, item.rarity,
                    100 if durable else None, 100 if durable else None,
                    max(1, 5 * (item.tier + 1)), item.description, start + offset,
                ),
            )
