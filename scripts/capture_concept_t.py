"""Capture the Concept T dashboard and Journal page in both shipped themes.

Usage: capture_concept_t.py [OUT] [--size 1280x720 ...] [--scale 75 100 150 ...]
Files are named <page>-<theme>-<width>x<height>-<scale>.png.
"""

from __future__ import annotations

import argparse
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


def settle(app, seconds: float = 0.3) -> None:  # type: ignore[no-untyped-def]
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default=str(ROOT / "artifacts" / "previews"))
    parser.add_argument("--size", nargs="+", default=["1600x900"])
    parser.add_argument("--scale", nargs="+", type=int, default=[100])
    parser.add_argument("--pages", nargs="+", default=["dashboard", "journal"])
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    config = Path(tempfile.mkdtemp(prefix="ddsim-capture-"))
    try:
        app, window, _manager = build_application([], config_dir=config)
        window.show()
        window._show_navigation("dashboard")
        for theme in ("high_fantasy", "modern_proof"):
            window.theme_selector.setCurrentIndex(window.theme_selector.findData(theme))
            settle(app, 1.5)
            for size in args.size:
                width, height = (int(part) for part in size.split("x"))
                window.resize(width, height)
                for scale in args.scale:
                    window.font_size_requested.emit(scale)
                    for page in args.pages:
                        window._show_navigation(page)
                        settle(app)
                        path = out / f"{page}-{theme}-{width}x{height}-{scale}.png"
                        window.grab().save(str(path))
                        print(path)
        window.font_size_requested.emit(100)
        window.close()
        app.processEvents()
    finally:
        shutil.rmtree(config, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
