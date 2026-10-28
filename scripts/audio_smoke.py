"""Manual check that QtMultimedia can load the packaged music and ambience.

Loads each context's first track and every ambience file in a QMediaPlayer (no
audio output, so nothing is heard), waits for Loaded, Buffered or Invalid, and
prints one line per file. Exit 1 if any file fails to load.

Usage: python scripts/audio_smoke.py   (not offscreen, DDSIM_DISABLE_AUDIO unset)
"""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtMultimedia import QMediaPlayer

from dd_simulator.ui.audio import AUDIO_ROOT, context_tracks, load_manifest


def main() -> int:
    app = QCoreApplication(sys.argv)
    manifest = load_manifest()
    jobs = [(context, context_tracks(manifest, context, False)[0]) for context in manifest["contexts"]]
    ambience = {
        entry["file"]
        for group in manifest["ambience"].values()
        for entries in group.values()
        for entry in entries
    }
    jobs += [("ambience", AUDIO_ROOT / file) for file in sorted(ambience)]
    done = {
        QMediaPlayer.MediaStatus.LoadedMedia,
        QMediaPlayer.MediaStatus.BufferedMedia,
        QMediaPlayer.MediaStatus.InvalidMedia,
    }
    failures = 0
    for context, path in jobs:
        player = QMediaPlayer()
        player.setSource(QUrl.fromLocalFile(str(path)))
        deadline = time.monotonic() + 10
        while player.mediaStatus() not in done and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        status = player.mediaStatus()
        ok = status in done - {QMediaPlayer.MediaStatus.InvalidMedia}
        failures += not ok
        print(f"{context:18} {path.relative_to(AUDIO_ROOT).as_posix():48} {status.name}"
              f" {player.duration() / 1000:.1f}s")
    print("all loaded" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
