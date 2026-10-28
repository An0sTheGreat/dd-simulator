"""Copy the Untitled RPG music and ambience into the packaged audio folder.

Every track under `Untitled RPG/Assets/Audio/Music` (including `Combat/`) and
`Audio/Ambience` is copied unchanged (no transcoding) to
`src/dd_simulator/ui/assets/audio/<context>/` or `audio/ambience/`. Every source is
checked before anything is written, and files whose bytes already match are left
untouched, so re-running the script changes nothing. Which file plays where is
decided by `audio/music_manifest.json`, not by this script.

Usage: python scripts/import_audio.py [UNTITLED_RPG_AUDIO_ROOT]
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = PROJECT_ROOT.parent.parent / "Untitled RPG" / "Assets" / "Audio"
AUDIO_ROOT = PROJECT_ROOT / "src" / "dd_simulator" / "ui" / "assets" / "audio"

# Target folder -> source paths relative to the Audio root. Contexts that reuse
# another context's file (travel_road, tavern_inn) point at it from the manifest.
JOBS: dict[str, tuple[str, ...]] = {
    "battle": (
        "Music/Combat/combat_1_better_tomorrow_metal.ogg",
        "Music/Combat/combat_2_better_tomorrow.ogg",
        "Music/Combat/combat_3_last_day_long.ogg",
        "Music/Combat/combat_4_last_day.ogg",
        "Music/Combat/combat_5_revenge.ogg",
        "Music/Combat/combat_6_ready.ogg",
        "Music/Combat/combat_7_survive.ogg",
        "Music/music_combat.wav",
    ),
    "boss": ("Music/music_boss.wav",),
    "exploration_cave": ("Music/music_cave.wav",),
    "forest_wilderness": (
        "Music/music_forest_day.mp3",
        "Music/music_forest_night.mp3",
        "Music/music_forest.wav",
    ),
    "town": (
        "Music/music_village_day.mp3",
        "Music/music_village_night.mp3",
        "Music/music_village.wav",
    ),
    "menu": ("Music/music_menu.mp3",),
    "ambience": (
        "Ambience/amb_cave.wav",
        "Ambience/amb_forest_day.wav",
        "Ambience/amb_forest_night.wav",
        "Ambience/amb_rain.wav",
        "Ambience/amb_village.wav",
    ),
}


def import_jobs(source_root: Path) -> list[tuple[Path, Path]]:
    return [
        (source_root / relative, AUDIO_ROOT / folder / Path(relative).name)
        for folder, sources in JOBS.items()
        for relative in sources
    ]


def main(argv: list[str]) -> int:
    source_root = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE_ROOT
    jobs = import_jobs(source_root)
    missing = [str(source) for source, _ in jobs if not source.is_file()]
    if missing:
        raise SystemExit("Missing source files:\n  " + "\n  ".join(missing))
    written = 0
    for source, target in jobs:
        if target.is_file() and target.read_bytes() == source.read_bytes():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written += 1
    total = sum(target.stat().st_size for _, target in jobs)
    print(f"{len(jobs)} tracks checked, {written} written, {total / 1_048_576:.1f} MB packaged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
