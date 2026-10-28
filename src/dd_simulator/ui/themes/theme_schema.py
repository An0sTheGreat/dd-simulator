"""Typed schema for external interface themes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class ThemeValidationError(ValueError):
    """Raised when a theme manifest is missing required data."""


REQUIRED_TOKEN_PATHS = (
    "colors.background_primary",
    "colors.background_secondary",
    "colors.panel_surface",
    "colors.text_primary",
    "colors.text_secondary",
    "colors.accent_primary",
    "colors.border_primary",
    "colors.selection",
    "typography.font_display",
    "typography.font_body",
    "typography.size_title",
    "typography.size_body",
    "spacing.space_sm",
    "spacing.space_md",
    "geometry.border_radius_small",
    "geometry.border_width",
    "geometry.panel_padding",
    "assets.panel_frame",
    "assets.header_frame",
    "assets.button_frame",
    "assets.minimap_frame",
    "assets.inventory_slot_background",
    "assets.selected_slot_overlay",
    "assets.divider_horizontal",
    "assets.divider_vertical",
    "assets.resource_health_icon",
    "assets.resource_mana_icon",
    "assets.resource_stamina_icon",
    # Concept T palette. codex.frame_* paths are relative to ui/assets; an empty value
    # means the theme draws no frame texture.
    "codex.ink",
    "codex.muted",
    "codex.gold",
    "codex.gold_dark",
    "codex.success",
    "codex.rarity_common",
    "codex.rarity_uncommon",
    "codex.rarity_rare",
    "codex.rarity_epic",
    "codex.rarity_legendary",
    "codex.bubble_player",
    "codex.bubble_player_border",
    "codex.bubble_npc",
    "codex.frame_panel_large",
    "codex.frame_panel_small",
    "codex.frame_tooltip",
    "codex.frame_slot",
    "codex.frame_slot_selected",
    "codex.frame_button_normal",
    "codex.frame_button_hover",
    "codex.frame_button_pressed",
    "codex.frame_button_disabled",
    "codex.frame_tab_normal",
    "codex.frame_tab_active",
    "codex.frame_divider",
    "codex.frame_ornamental_corner",
    "codex.frame_quest_tracker",
    "codex.frame_progress_bar",
    "codex.frame_rarity_common",
    "codex.frame_rarity_uncommon",
    "codex.frame_rarity_rare",
    "codex.frame_rarity_epic",
    "codex.frame_rarity_legendary",
)


def flatten_tokens(values: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten nested theme tokens into dotted QSS placeholder keys."""

    flattened: dict[str, str] = {}
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flattened.update(flatten_tokens(value, path))
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            flattened[path] = str(value)
        else:
            raise ThemeValidationError(f"Token {path!r} must be a string or number")
    return flattened


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    """Validated theme metadata and tokens."""

    schema_version: int
    theme_id: str
    name: str
    description: str
    author: str
    version: str
    tokens: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ThemeDefinition":
        required_fields = (
            "schema_version",
            "theme_id",
            "name",
            "description",
            "author",
            "version",
            "tokens",
        )
        missing = [field for field in required_fields if field not in raw]
        if missing:
            raise ThemeValidationError(f"Missing theme fields: {', '.join(missing)}")

        schema_version = raw["schema_version"]
        if schema_version != 1:
            raise ThemeValidationError(f"Unsupported theme schema: {schema_version!r}")

        theme_id = raw["theme_id"]
        if not isinstance(theme_id, str) or not theme_id.replace("_", "").isalnum():
            raise ThemeValidationError("theme_id must contain only letters, numbers, and underscores")

        for field in ("name", "description", "author", "version"):
            if not isinstance(raw[field], str) or not raw[field].strip():
                raise ThemeValidationError(f"{field} must be a non-empty string")

        tokens = raw["tokens"]
        if not isinstance(tokens, Mapping):
            raise ThemeValidationError("tokens must be an object")
        flattened = flatten_tokens(tokens)
        missing_tokens = [path for path in REQUIRED_TOKEN_PATHS if path not in flattened]
        if missing_tokens:
            raise ThemeValidationError(
                "Missing required theme tokens: " + ", ".join(missing_tokens)
            )

        return cls(
            schema_version=schema_version,
            theme_id=theme_id,
            name=raw["name"].strip(),
            description=raw["description"].strip(),
            author=raw["author"].strip(),
            version=raw["version"].strip(),
            tokens=tokens,
        )
