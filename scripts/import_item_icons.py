"""Import the mapped item icons from the owner's icon library.

Reads the `sources` section of `ui/assets/icons/item_icon_manifest.json` (packaged name
to a path relative to `Project Resources/assets`), downscales each CraftPix painting to a
128 px PNG at `ui/assets/icons/library/<name>`, and removes any PNG there that the
manifest no longer maps. Every source is checked before anything is written, and files
whose bytes already match are left untouched, so re-running the script changes nothing.

Usage: python scripts/import_item_icons.py [PROJECT_RESOURCES_ASSETS_ROOT]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from import_codex_assets import _downscaled_png


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = PROJECT_ROOT.parent / "Project Resources" / "assets"
ICON_ROOT = PROJECT_ROOT / "src" / "dd_simulator" / "ui" / "assets" / "icons"
MANIFEST_PATH = ICON_ROOT / "item_icon_manifest.json"
LIBRARY_ROOT = ICON_ROOT / "library"
ICON_SIZE = 128


def import_jobs(source_root: Path) -> list[tuple[Path, Path]]:
    """Return (library source, packaged target) for every mapped icon."""

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    unknown = sorted(set(manifest["records"].values()) - set(manifest["sources"]))
    if unknown:
        raise SystemExit("Records map to icons without a source:\n  " + "\n  ".join(unknown))
    for name in manifest["sources"]:
        target = LIBRARY_ROOT / name
        if Path(name).is_absolute() or ".." in Path(name).parts or (
            target.resolve().parent != LIBRARY_ROOT.resolve()
        ):
            raise SystemExit(f"Icon name escapes the library folder: {name}")
    return [
        (source_root / relative, LIBRARY_ROOT / name)
        for name, relative in manifest["sources"].items()
    ]


def main(argv: list[str]) -> int:
    source_root = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE_ROOT
    jobs = import_jobs(source_root)
    missing = [str(source) for source, _ in jobs if not source.is_file()]
    if missing:
        raise SystemExit("Missing source files:\n  " + "\n  ".join(missing))

    written = 0
    for source, target in jobs:
        data = _downscaled_png(source, ICON_SIZE)
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written += 1
    targets = {target for _, target in jobs}
    stale = [path for path in LIBRARY_ROOT.glob("*.png") if path not in targets]
    for path in stale:
        path.unlink()
    print(f"{len(jobs)} icons checked, {written} written, {len(stale)} removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
