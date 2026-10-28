"""Capture the Concept T dashboard at 1600x900 in both shipped themes."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dd_simulator.app import build_application  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "previews"
    out.mkdir(parents=True, exist_ok=True)
    config = Path(tempfile.mkdtemp(prefix="ddsim-capture-"))
    try:
        app, window, _manager = build_application([], config_dir=config)
        window.resize(1600, 900)
        window.show()
        window._show_navigation("dashboard")
        for theme in ("high_fantasy", "modern_proof"):
            window.theme_selector.setCurrentIndex(window.theme_selector.findData(theme))
            end = time.monotonic() + 1.5
            while time.monotonic() < end:
                app.processEvents()
            path = out / f"window-{theme}.png"
            window.grab().save(str(path))
            print(path)
        window.close()
        app.processEvents()
    finally:
        shutil.rmtree(config, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
