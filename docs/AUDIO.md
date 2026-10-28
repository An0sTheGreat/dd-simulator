# Music and ambience

`src/dd_simulator/ui/audio.py` plays context music and a looping ambience bed on
QtMultimedia. Which file plays where lives in
`src/dd_simulator/ui/assets/audio/music_manifest.json`; replacing a track is a manifest
edit or a file swap, never a code change.

## Manifest format

```json
{
  "contexts": {
    "forest_wilderness": [
      {"file": "forest_wilderness/music_forest_day.mp3", "time": "day"},
      {"file": "forest_wilderness/music_forest_night.mp3", "time": "night"}
    ],
    "menu": [{"file": "menu/music_menu.mp3"}]
  },
  "ambience": {
    "weather": {"rain": [{"file": "ambience/amb_rain.wav"}]},
    "biome": {"forest": [{"file": "ambience/amb_forest_day.wav", "time": "day"}]}
  }
}
```

- `file` is relative to `ui/assets/audio/`. Any format QtMultimedia (FFmpeg) loads works:
  MP3, OGG, WAV.
- `time` is optional: `day` or `night`. An entry without `time` plays at any hour. If no
  entry matches the hour, all entries of that list are used.
- Contexts: `battle`, `boss`, `travel_road`, `forest_wilderness`, `town`, `tavern_inn`,
  `exploration_cave`, `menu`. `battle` rotates: each track plays once, then a different
  one follows, never the same twice in a row. Every other context loops its track.
- Ambience `biome` keys are location archetypes (`ui/location_images.py`). `weather` keys
  are the weather variants `rain`, `snow` and `fog`; outdoors a matching weather entry
  replaces the biome bed. Caves, dungeons and taverns ignore weather.

## Selection

1. Settings, character creation and Local AI setup: `menu`.
2. Active combat: `boss` when an active enemy's archetype is tier 4 (`BOSS_TIER`), else
   `battle`. Encounters have no boss or elite flag.
3. Otherwise the location archetype: road and mountain → `travel_road`; forest and swamp
   → `forest_wilderness`; village, town and castle → `town`; tavern and inn →
   `tavern_inn`; cave and dungeon → `exploration_cave`. Unknown → `travel_road`.
4. Night when the clock reads Night; otherwise day.

A context change crossfades over about 2 s. Music volume, ambience volume and mute are
UI preferences (`music_volume`, `ambience_volume`, `audio_muted`) on the Settings page.

## Silence and failure

No players are created when `QT_QPA_PLATFORM=offscreen` or `DDSIM_DISABLE_AUDIO=1`, and
every `--smoke-test*` run sets `DDSIM_DISABLE_AUDIO=1`. Playback errors are logged and
never shown. `scripts/audio_smoke.py` (not offscreen) loads each context's first track and
every ambience file and prints its media status.

## Importing

`scripts/import_audio.py [UNTITLED_RPG_AUDIO_ROOT]` copies the Untitled RPG tracks
unchanged into the context folders. It checks every source first and skips files whose
bytes already match.
