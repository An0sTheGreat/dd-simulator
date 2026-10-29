"""Theme package discovery, QSS compilation, application, and preferences."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from dd_simulator.ui.themes.theme_schema import (
    ThemeDefinition,
    ThemeValidationError,
    flatten_tokens,
)


LOGGER = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")
URL_PATTERN = re.compile(r'url\(["\']?(?P<path>[^)"\']+)["\']?\)')
FONT_SIZE_PATTERN = re.compile(
    r"(?P<prefix>font-size\s*:\s*)(?P<size>\d+(?:\.\d+)?)(?P<unit>px|pt)",
    re.IGNORECASE,
)


class StylesheetTarget(Protocol):
    """The minimal Qt application surface used by ThemeManager."""

    def setStyleSheet(self, stylesheet: str) -> None: ...


@dataclass(frozen=True, slots=True)
class LoadedTheme:
    definition: ThemeDefinition
    directory: Path
    stylesheet: str


class ThemeManager:
    """Load themes without coupling theme data to widget behavior."""

    def __init__(
        self,
        *,
        themes_root: Path,
        preferences_path: Path,
        default_theme_id: str,
    ) -> None:
        self.themes_root = Path(themes_root)
        self.preferences_path = Path(preferences_path)
        self.default_theme_id = default_theme_id
        self.current_theme_id: str | None = None
        self.font_scale = 1.0
        self._current_theme: LoadedTheme | None = None
        self._applied: tuple[object, float, object] | None = None  # theme, scale, target
        self._change_listeners: list[Callable[[LoadedTheme], None]] = []

    def _read_theme(self, directory: Path) -> LoadedTheme:
        manifest_path = directory / "theme.json"
        stylesheet_path = directory / "theme.qss"
        if not manifest_path.is_file() or not stylesheet_path.is_file():
            raise ThemeValidationError(
                f"Theme directory {directory.name!r} requires theme.json and theme.qss"
            )

        with manifest_path.open("r", encoding="utf-8") as stream:
            raw = json.load(stream)
        if not isinstance(raw, dict):
            raise ThemeValidationError("Theme manifest root must be an object")
        definition = ThemeDefinition.from_mapping(raw)
        if definition.theme_id != directory.name:
            raise ThemeValidationError(
                f"Theme id {definition.theme_id!r} must match directory {directory.name!r}"
            )

        qss_template = stylesheet_path.read_text(encoding="utf-8")
        stylesheet = self.compile_stylesheet(qss_template, definition)

        def resolve_url(match: re.Match[str]) -> str:
            raw_path = match.group("path").strip()
            if raw_path.startswith(":") or Path(raw_path).is_absolute():
                return match.group(0)
            return f'url("{(directory / raw_path).resolve().as_posix()}")'

        stylesheet = URL_PATTERN.sub(resolve_url, stylesheet)
        return LoadedTheme(definition, directory.resolve(), stylesheet)

    def discover(self) -> dict[str, LoadedTheme]:
        """Return all valid installed themes, keyed by stable theme ID."""

        discovered: dict[str, LoadedTheme] = {}
        if not self.themes_root.is_dir():
            return discovered
        for directory in sorted(
            path
            for path in self.themes_root.iterdir()
            if path.is_dir() and not path.name.startswith((".", "__"))
        ):
            try:
                loaded = self._read_theme(directory)
            except (OSError, json.JSONDecodeError, ThemeValidationError) as exc:
                LOGGER.warning("Ignoring invalid theme at %s: %s", directory, exc)
                continue
            discovered[loaded.definition.theme_id] = loaded
        return discovered

    def available_themes(self) -> list[ThemeDefinition]:
        """Return validated theme metadata in display order."""

        return [item.definition for item in self.discover().values()]

    def add_change_listener(self, listener: Callable[[LoadedTheme], None]) -> None:
        """Notify a UI coordinator when stylesheet or theme assets change."""

        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    def remove_change_listener(self, listener: Callable[[LoadedTheme], None]) -> None:
        """Stop notifying a previously registered theme listener."""

        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def resolve_asset_path(
        self,
        loaded: LoadedTheme,
        asset_name: str,
        *,
        fallback_to_default: bool = True,
    ) -> Path | None:
        """Resolve a named theme asset safely, with default-theme fallback."""

        assets = loaded.definition.tokens.get("assets")
        raw_path = assets.get(asset_name) if isinstance(assets, Mapping) else None
        if isinstance(raw_path, str) and raw_path.strip():
            theme_root = loaded.directory.resolve()
            candidate = (theme_root / raw_path).resolve()
            try:
                candidate.relative_to(theme_root)
            except ValueError:
                LOGGER.warning(
                    "Ignoring theme asset outside %s: %s",
                    theme_root,
                    raw_path,
                )
            else:
                if candidate.is_file():
                    return candidate

        if fallback_to_default and loaded.definition.theme_id != self.default_theme_id:
            default = self.load_theme(self.default_theme_id)
            return self.resolve_asset_path(
                default,
                asset_name,
                fallback_to_default=False,
            )
        LOGGER.debug(
            "Theme asset %r is unavailable for %s; widget fallback remains active",
            asset_name,
            loaded.definition.theme_id,
        )
        return None

    @staticmethod
    def compile_stylesheet(template: str, definition: ThemeDefinition) -> str:
        """Replace all QSS token placeholders or fail on an unknown token."""

        tokens = flatten_tokens(definition.tokens)

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in tokens:
                raise ThemeValidationError(f"Stylesheet references unknown token {key!r}")
            return tokens[key]

        compiled = TOKEN_PATTERN.sub(replace, template)
        unresolved = TOKEN_PATTERN.findall(compiled)
        if unresolved:
            raise ThemeValidationError(f"Unresolved stylesheet tokens: {unresolved}")
        return compiled

    def load_theme(self, theme_id: str | None) -> LoadedTheme:
        """Load a requested theme, falling back safely to the default."""

        themes = self.discover()
        if theme_id and theme_id in themes:
            return themes[theme_id]
        if theme_id and theme_id != self.default_theme_id:
            LOGGER.warning("Theme %r is unavailable; using %r", theme_id, self.default_theme_id)
        try:
            return themes[self.default_theme_id]
        except KeyError as exc:
            raise ThemeValidationError(
                f"Default theme {self.default_theme_id!r} is missing or invalid"
            ) from exc

    def load_preferred_theme(self) -> LoadedTheme:
        """Load the saved theme choice, with corruption-safe fallback."""

        preferred: str | None = None
        try:
            with self.preferences_path.open("r", encoding="utf-8") as stream:
                raw: Any = json.load(stream)
            if isinstance(raw, dict) and isinstance(raw.get("theme_id"), str):
                preferred = raw["theme_id"]
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Could not read theme preference %s: %s", self.preferences_path, exc)
        return self.load_theme(preferred)

    def save_preference(self, theme_id: str) -> None:
        """Persist the selected theme using an atomic file replacement."""

        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.preferences_path.with_suffix(self.preferences_path.suffix + ".tmp")
        root: dict[str, Any] = {}
        try:
            raw = json.loads(self.preferences_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                root = raw
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning(
                "Could not preserve existing preferences %s: %s",
                self.preferences_path,
                exc,
            )
        root["theme_id"] = theme_id
        temporary.write_text(
            json.dumps(root, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.preferences_path)

    def apply_loaded_theme(
        self,
        application: StylesheetTarget,
        loaded: LoadedTheme,
        *,
        persist: bool,
    ) -> None:
        application.setStyleSheet(self.scale_font_sizes(loaded.stylesheet, self.font_scale))
        self._applied = (loaded, self.font_scale, application)
        if hasattr(application, "setProperty"):
            application.setProperty("themeId", loaded.definition.theme_id)
        self.current_theme_id = loaded.definition.theme_id
        self._current_theme = loaded
        if persist:
            self.save_preference(loaded.definition.theme_id)
        for listener in tuple(self._change_listeners):
            listener(loaded)

    def apply_theme(self, application: StylesheetTarget, theme_id: str) -> LoadedTheme:
        """Load, apply, and remember a theme selection."""

        loaded = self.load_theme(theme_id)
        self.apply_loaded_theme(application, loaded, persist=True)
        return loaded

    @staticmethod
    def scale_font_sizes(stylesheet: str, scale: float) -> str:
        """Scale explicit QSS font sizes while preserving each theme's hierarchy."""

        bounded = min(1.5, max(0.75, float(scale)))

        def replace(match: re.Match[str]) -> str:
            line_end = stylesheet.find("\n", match.end())
            if line_end < 0:
                line_end = len(stylesheet)
            if "font-scale-fixed" in stylesheet[match.start():line_end]:
                return match.group(0)
            original = float(match.group("size"))
            scaled = max(1, round(original * bounded))
            return f'{match.group("prefix")}{scaled}{match.group("unit")}'

        return FONT_SIZE_PATTERN.sub(replace, stylesheet)

    def set_font_scale(
        self,
        application: StylesheetTarget,
        scale: float,
    ) -> None:
        """Apply a live font scale and retain it across later theme changes."""

        scale = min(1.5, max(0.75, float(scale)))
        # re-applying an unchanged stylesheet re-polishes every widget for nothing
        if self._current_theme is not None and self._applied == (self._current_theme, scale, application):
            return
        self.font_scale = scale
        if self._current_theme is not None:
            application.setStyleSheet(
                self.scale_font_sizes(self._current_theme.stylesheet, self.font_scale)
            )
            self._applied = (self._current_theme, self.font_scale, application)
