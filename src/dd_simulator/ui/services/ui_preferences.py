"""Corruption-safe persistence for presentation-only UI preferences."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


class UiPreferencesStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _read_root(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Could not read UI preferences %s: %s", self.path, exc)
            return {}
        return raw if isinstance(raw, dict) else {}

    def load_ui(self) -> dict[str, Any]:
        ui = self._read_root().get("ui")
        return dict(ui) if isinstance(ui, dict) else {}

    def save_ui(self, values: dict[str, Any]) -> None:
        root = self._read_root()
        root["ui"] = values
        self._write_root(root)

    def reset_ui(self) -> None:
        root = self._read_root()
        root.pop("ui", None)
        self._write_root(root)

    def load_lm_studio(self) -> dict[str, Any]:
        values = self._read_root().get("lm_studio")
        return dict(values) if isinstance(values, dict) else {}

    def save_lm_studio(self, values: dict[str, Any]) -> None:
        root = self._read_root()
        root["lm_studio"] = values
        self._write_root(root)

    def load_local_ai(self) -> dict[str, Any]:
        values = self._read_root().get("local_ai")
        return dict(values) if isinstance(values, dict) else {}

    def save_local_ai(self, values: dict[str, Any]) -> None:
        root = self._read_root()
        root["local_ai"] = values
        self._write_root(root)

    def _write_root(self, root: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(root, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
