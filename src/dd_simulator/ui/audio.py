"""Context-driven music and ambience on QtMultimedia.

Selection (which context, which track, which ambience) is pure functions over the
dashboard view and `assets/audio/music_manifest.json`; `MusicController` only plays
what they choose. Audio failure is logged and otherwise silent.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import random
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QGuiApplication

from dd_simulator.state.encounters import archetype_by_key
from dd_simulator.ui.location_images import (
    INDOOR_ARCHETYPES,
    LOCATION_ARCHETYPES,
    _archetype,
    _time_variants,
    _weather_variants,
)
from dd_simulator.ui.models.presentation import DashboardView


LOGGER = logging.getLogger(__name__)
AUDIO_ROOT = Path(__file__).parent / "assets" / "audio"
MANIFEST_PATH = AUDIO_ROOT / "music_manifest.json"
MENU_PAGES = {"settings", "character_creation", "local_ai_setup"}
BIOME_CONTEXTS = {
    "castle": "town",
    "cave": "exploration_cave",
    "dungeon": "exploration_cave",
    "forest": "forest_wilderness",
    "mountain": "travel_road",
    "road": "travel_road",
    "swamp": "forest_wilderness",
    "tavern": "tavern_inn",
    "village": "town",
}
assert set(BIOME_CONTEXTS) == LOCATION_ARCHETYPES
# Encounters carry no boss flag; an active enemy of the top archetype tier counts.
BOSS_TIER = 4
ROTATING_CONTEXTS = {"battle"}
CROSSFADE_MS = 2000
FADE_STEP_MS = 50
DEFAULT_MUSIC_VOLUME = 35
DEFAULT_AMBIENCE_VOLUME = 30


def output_gain(percent: float) -> float:
    """Slider percent (0-100) to linear output gain, on a perceptual (logarithmic) curve.

    Linear gain makes the lower half of the slider near full loudness; 50 maps to about 0.15.
    """
    from PySide6.QtMultimedia import QtAudio

    scale = QtAudio.VolumeScale
    gain = QtAudio.convertVolume(percent / 100, scale.LogarithmicVolumeScale, scale.LinearVolumeScale)
    return max(0.0, gain)


def audio_disabled() -> bool:
    app = QGuiApplication.instance()
    return (
        os.environ.get("DDSIM_DISABLE_AUDIO") == "1"
        or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        or (app is not None and app.platformName() in ("offscreen", "minimal"))
    )


def _guarded(method: Any) -> Any:
    """Log and swallow errors: audio must never take the UI down."""

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return method(self, *args, **kwargs)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Audio %s failed", method.__name__)
            return None

    return wrapper


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Music manifest %s unreadable: %s", path, exc)
        return {}
    return manifest if isinstance(manifest, dict) else {}


def is_boss_encounter(combat: Any) -> bool:
    for combatant in combat.combatants:
        archetype = archetype_by_key(combatant.archetype_key)
        if (
            combatant.side == "enemy"
            and combatant.status == "active"
            and archetype is not None
            and archetype.tier >= BOSS_TIER
        ):
            return True
    return False


def location_archetype(dashboard: DashboardView) -> str:
    return _archetype(dashboard.location.biome, dashboard.location.name)


def select_context(page: str, dashboard: DashboardView | None) -> str:
    if dashboard is None or page in MENU_PAGES:
        return "menu"
    combat = dashboard.combat
    if combat is not None and combat.status == "active":
        return "boss" if is_boss_encounter(combat) else "battle"
    return BIOME_CONTEXTS.get(location_archetype(dashboard), "travel_road")


def is_night(time_label: str) -> bool:
    return _time_variants(time_label) == ["night"]


def _timed(entries: Any, night: bool) -> list[Path]:
    if not isinstance(entries, list):
        return []
    wanted = "night" if night else "day"
    valid = [entry for entry in entries if isinstance(entry, dict) and entry.get("file")]
    matching = [entry for entry in valid if entry.get("time") in (None, wanted)] or valid
    return [AUDIO_ROOT / str(entry["file"]) for entry in matching]


def context_tracks(manifest: dict[str, Any], context: str, night: bool) -> list[Path]:
    return _timed(manifest.get("contexts", {}).get(context), night)


def select_ambience(
    manifest: dict[str, Any], archetype: str, weather: str, night: bool
) -> Path | None:
    ambience = manifest.get("ambience", {})
    tracks: list[Path] = []
    if archetype not in INDOOR_ARCHETYPES | {"cave"}:
        for variant in _weather_variants(weather):
            tracks = _timed(ambience.get("weather", {}).get(variant), night)
    if not tracks:
        tracks = _timed(ambience.get("biome", {}).get(archetype), night)
    return tracks[0] if tracks else None


def next_track(
    tracks: list[Path], previous: Path | None, rng: random.Random | None = None
) -> Path | None:
    """Pick a track at random, never `previous` when there is any other choice."""

    choices = [track for track in tracks if track != previous] or tracks
    return (rng or random).choice(choices) if choices else None


class MusicController(QObject):
    """Plays the selected context's music with a crossfade, plus looping ambience."""

    def __init__(self, parent: QObject | None = None, *, enabled: bool | None = None) -> None:
        super().__init__(parent)
        self.enabled = (not audio_disabled()) if enabled is None else enabled
        self.manifest = load_manifest()
        self.music_volume = DEFAULT_MUSIC_VOLUME
        self.ambience_volume = DEFAULT_AMBIENCE_VOLUME
        self.muted = False
        self.context = ""
        self.track: Path | None = None
        self.ambience: Path | None = None
        self.players: list[Any] = []
        self._tracks: list[Path] = []
        self._fade = 1.0  # incoming player level
        self._fade_out = 0.0  # outgoing player level
        self._fade_target = 1.0
        self._last_track_by_context: dict[str, Path] = {}
        self._invalid_skips = 0
        if not self.enabled:
            return
        try:
            self._create_players()
        except Exception:  # noqa: BLE001 - audio must never take the UI down
            LOGGER.exception("Audio unavailable; continuing silently")
            self.enabled = False
            self.players = []

    def _create_players(self) -> None:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        def player() -> Any:
            media = QMediaPlayer(self)
            output = QAudioOutput(self)
            media.setAudioOutput(output)
            media.errorOccurred.connect(
                lambda _error, message, media=media: LOGGER.warning(
                    "Audio playback failed for %s: %s", media.source().toLocalFile(), message
                )
            )
            return media

        self._music = [player(), player()]
        self._ambience_player = player()
        self._ambience_player.setLoops(QMediaPlayer.Loops.Infinite)
        for media in self._music:
            media.mediaStatusChanged.connect(self._media_status_changed)
        self.players = [*self._music, self._ambience_player]
        self._end_status = QMediaPlayer.MediaStatus.EndOfMedia
        self._invalid_status = QMediaPlayer.MediaStatus.InvalidMedia
        self._loaded_status = QMediaPlayer.MediaStatus.LoadedMedia
        self._infinite = QMediaPlayer.Loops.Infinite
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(FADE_STEP_MS)
        self._fade_timer.timeout.connect(self._fade_step)

    @_guarded
    def update(self, page: str, dashboard: DashboardView | None) -> None:
        """Follow the game state; a no-op when audio is disabled."""

        if self.enabled:
            self._update(page, dashboard)

    def _next_in_context(self) -> Path | None:
        return next_track(self._tracks, self._last_track_by_context.get(self.context))

    def _update(self, page: str, dashboard: DashboardView | None) -> None:
        context = select_context(page, dashboard)
        night = dashboard is not None and is_night(dashboard.location.time_label)
        tracks = context_tracks(self.manifest, context, night)
        self._tracks = tracks
        stale = self.track not in tracks and (tracks or self.track is not None)
        if context != self.context or (context not in ROTATING_CONTEXTS and stale):
            self.context = context
            self._crossfade_to(self._next_in_context())
        ambience = None
        if dashboard is not None and context != "menu":
            ambience = select_ambience(
                self.manifest, location_archetype(dashboard), dashboard.location.weather, night
            )
        if ambience != self.ambience:
            self.ambience = ambience
            self._ambience_player.stop()
            if ambience is not None:
                self._ambience_player.setSource(QUrl.fromLocalFile(str(ambience)))
                self._ambience_player.play()
        self._apply_volumes()

    def _crossfade_to(self, track: Path | None) -> None:
        self.track = track
        if track is not None:
            self._last_track_by_context[self.context] = track
        outgoing, incoming = self._music
        self._music = [incoming, outgoing]
        # Players swap roles but keep their current levels, so the volume never jumps.
        self._fade, self._fade_out = self._fade_out, self._fade
        if track is not None:
            incoming.setSource(QUrl.fromLocalFile(str(track)))
            incoming.setLoops(1 if self.context in ROTATING_CONTEXTS else self._infinite)
            incoming.play()
        else:
            incoming.stop()
            self._fade = 0.0
        self._fade_target = 1.0 if track is not None else 0.0
        self._fade_timer.start()
        self._apply_volumes()

    @_guarded
    def _fade_step(self) -> None:
        step = FADE_STEP_MS / CROSSFADE_MS
        if self._fade < self._fade_target:
            self._fade = min(self._fade_target, self._fade + step)
        self._fade_out = max(0.0, self._fade_out - step)
        if self._fade >= self._fade_target and self._fade_out <= 0.0:
            self._fade_timer.stop()
            self._music[1].stop()
        self._apply_volumes()

    @_guarded
    def _media_status_changed(self, status: Any) -> None:
        if self.sender() is not self._music[0]:
            return
        if status == self._loaded_status:
            self._invalid_skips = 0
        # Rotating contexts play each track once, then move to a different one; an
        # unplayable file is skipped too, unless every track has failed in a row.
        rotating = self.context in ROTATING_CONTEXTS
        if status == self._end_status and rotating:
            self._crossfade_to(self._next_in_context())
        elif status == self._invalid_status and rotating and self._invalid_skips < len(self._tracks):
            self._invalid_skips += 1
            self._crossfade_to(self._next_in_context())

    @_guarded
    def set_volumes(self, music: int, ambience: int, muted: bool) -> None:
        self.music_volume = min(100, max(0, int(music)))
        self.ambience_volume = min(100, max(0, int(ambience)))
        self.muted = bool(muted)
        if self.enabled:
            self._apply_volumes()

    def _apply_volumes(self) -> None:
        scale = 0.0 if self.muted else 1.0
        music = scale * output_gain(self.music_volume)
        incoming, outgoing = self._music
        incoming.audioOutput().setVolume(music * self._fade)
        outgoing.audioOutput().setVolume(music * self._fade_out)
        self._ambience_player.audioOutput().setVolume(scale * output_gain(self.ambience_volume))

    @_guarded
    def stop(self) -> None:
        if not self.enabled:
            return
        self._fade_timer.stop()
        for media in self.players:
            media.stop()
