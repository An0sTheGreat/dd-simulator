"""Resolve packaged location artwork from location state."""

from __future__ import annotations

from pathlib import Path


LOCATION_ART_ROOT = Path(__file__).parent / "assets" / "location"
INDOOR_ARCHETYPES = {"dungeon", "tavern"}
LOCATION_ARCHETYPES = {
    "castle", "cave", "dungeon", "forest", "mountain", "road", "swamp", "tavern", "village"
}

ARCHETYPE_ALIASES = {
    "cavern": "cave",
    "city": "village",
    "crypt": "dungeon",
    "fortress": "castle",
    "hamlet": "village",
    "inn": "tavern",
    "keep": "castle",
    "mill": "village",
    "orchard": "forest",
    "path": "road",
    "ruins": "dungeon",
    "town": "village",
    "woodland": "forest",
    "woods": "forest",
}


def resolve_location_image(
    *,
    name: str,
    biome: str,
    time_label: str,
    weather: str,
    danger: str,
    root: Path = LOCATION_ART_ROOT,
) -> Path | None:
    """Return the closest packaged image, or None when no archetype exists."""

    archetype = _archetype(biome, name)
    if not archetype:
        return None
    variants = _danger_variants(danger)
    if archetype not in INDOOR_ARCHETYPES:
        variants.extend(_weather_variants(weather))
        variants.extend(_time_variants(time_label))
    variants.append("base")
    folder = root / archetype
    for variant in dict.fromkeys(variants):
        candidate = folder / f"{archetype}_{variant}.png"
        if candidate.is_file():
            return candidate
    return None


def _archetype(biome: str, name: str) -> str:
    words = f"{biome} {name}".casefold().replace("-", " ").split()
    for word in words:
        normalized = ARCHETYPE_ALIASES.get(word, word)
        if normalized in LOCATION_ARCHETYPES:
            return normalized
    return ""


def _danger_variants(value: str) -> list[str]:
    lowered = value.casefold()
    variants: list[str] = []
    for variant, words in (
        ("danger_fire", ("fire", "flame", "burning", "ash")),
        ("danger_smoke", ("smoke", "smolder")),
        ("danger_blood", ("blood", "gore", "slaughter")),
        ("danger_corruption", ("corrupt", "blight", "curse", "taint")),
        ("fog", ("fog", "mist")),
    ):
        if any(word in lowered for word in words):
            variants.append(variant)
    return variants


def _weather_variants(value: str) -> list[str]:
    lowered = value.casefold()
    for variant, words in (
        ("snow", ("snow", "blizzard", "sleet", "winter")),
        ("rain", ("rain", "storm", "thunder", "downpour")),
        ("fog", ("fog", "mist")),
    ):
        if any(word in lowered for word in words):
            return [variant]
    return []


def _time_variants(value: str) -> list[str]:
    lowered = value.casefold()
    for variant, words in (
        ("night", ("night", "midnight")),
        ("sunset", ("sunset", "dusk", "evening")),
        ("dawn", ("dawn", "sunrise")),
        ("daylight", ("morning", "day", "noon", "afternoon")),
    ):
        if any(word in lowered for word in words):
            return [variant]
    return []
