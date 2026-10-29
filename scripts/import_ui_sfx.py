"""Import the interface sound effects as short WAVs.

Usage: python scripts/import_ui_sfx.py [UNTITLED_RPG_ASSETS_ROOT]
Decodes each chosen clip with QtMultimedia, writes 44.1 kHz mono 16-bit WAV (what
QSoundEffect plays with low latency) to src/dd_simulator/ui/assets/audio/ui/<event>.wav,
peak-levels every clip to the same height, and records provenance in sources.json.
All sources are CC0 or the Untitled RPG project's own synthesis; no combat, spell or
ability sounds are imported.
"""

from __future__ import annotations

import hashlib
import json
import sys
import wave
from array import array
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS = PROJECT_ROOT.parent.parent / "Untitled RPG" / "Assets"
OUT = PROJECT_ROOT / "src" / "dd_simulator" / "ui" / "assets" / "audio" / "ui"
RATE = 44100
PEAK = 0.6  # of full scale; interface sounds sit under the music

KENNEY = ("Kenney", "https://kenney.nl/assets/rpg-audio", "CC0-1.0")
RPG_SFX = ("80-CC0-RPG-SFX via Untitled RPG Tools/build_sfx_pack.py", "", "CC0-1.0")
ORIGINAL = ("Untitled RPG project, original synthesis (generate_audio.py)", "", "original")
# event -> (path below the Assets root, credit)
CLIPS = {
    "hover": ("Audio/SFX/UI/ui_hover_1.wav", ORIGINAL),
    "click": ("Audio/SFX/Supplied/UI/ui_click_1.ogg", RPG_SFX),
    "page": (".CC0 Assets/Audio/SFX/KenneyRPGAudio/bookFlip1.ogg", KENNEY),
    "pickup": (".CC0 Assets/Audio/SFX/KenneyRPGAudio/handleSmallLeather.ogg", KENNEY),
    "drop": (".CC0 Assets/Audio/SFX/KenneyRPGAudio/dropLeather.ogg", KENNEY),
    "equip": (".CC0 Assets/Audio/SFX/KenneyRPGAudio/beltHandle1.ogg", KENNEY),
    "unequip": (".CC0 Assets/Audio/SFX/KenneyRPGAudio/cloth2.ogg", KENNEY),
    "coins": (".CC0 Assets/Audio/SFX/KenneyRPGAudio/handleCoins.ogg", KENNEY),
    "deny": ("Audio/SFX/Supplied/UI/ui_deny_1.ogg", RPG_SFX),
}


def decode(path: Path) -> array:
    decoder = QAudioDecoder()
    fmt = QAudioFormat()
    fmt.setSampleRate(RATE)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    decoder.setAudioFormat(fmt)
    decoder.setSource(QUrl.fromLocalFile(str(path)))
    data = bytearray()
    decoder.bufferReady.connect(lambda: data.extend(bytes(decoder.read().constData())))
    loop = QEventLoop()
    decoder.finished.connect(loop.quit)
    failed: list[str] = []
    decoder.error.connect(lambda _e: (failed.append(decoder.errorString()), loop.quit()))
    QTimer.singleShot(10_000, loop.quit)
    decoder.start()
    loop.exec()
    if failed or not data:
        raise RuntimeError(f"Could not decode {path}: {failed or 'no audio'}")
    samples = array("h")
    samples.frombytes(bytes(data))
    return samples


def level(samples: array) -> array:
    peak = max(1, max(abs(value) for value in samples))
    gain = PEAK * 32767 / peak
    return array("h", (max(-32768, min(32767, round(value * gain))) for value in samples))


def main() -> int:
    _app = QCoreApplication.instance() or QCoreApplication([])
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ASSETS
    OUT.mkdir(parents=True, exist_ok=True)
    sources = {}
    for event, (relative, (author, url, license_)) in CLIPS.items():
        source = root / relative
        samples = level(decode(source))
        with wave.open(str(OUT / f"{event}.wav"), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(samples.tobytes())
        sources[f"{event}.wav"] = {
            "source": relative,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "author": author,
            "url": url,
            "license": license_,
        }
        print(f"{event}: {source.name} ({len(samples) / RATE:.2f} s)")
    (OUT / "sources.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
