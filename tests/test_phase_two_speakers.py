"""Phase 2a: optional NPC speaker on transcript messages (schema 22, D8)."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from dd_simulator.local_model.action_resolver import (
    TURN_RESPONSE_FORMAT,
    LocalModelActionResolver,
)
from dd_simulator.state import GameStateDatabase, GameStateService
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, seed_demo_campaign
from dd_simulator.state.turns import ActionOutcome, NarrativeSegment

MERCHANT = "npc-roadside-merchant"


def _file_service(tmp_path: Path) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase(tmp_path / "game-state.db")
    service = GameStateService(database)
    assert service.initialize() == LATEST_SCHEMA_VERSION
    service.ensure_demo_campaign()
    return database, service


def test_schema_21_transcript_migrates_with_null_speaker_and_backup(tmp_path: Path) -> None:
    path = tmp_path / "schema-21.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    for version, sql in MIGRATIONS[:21]:
        connection.executescript(sql)
        connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
    connection.execute("INSERT INTO campaigns(id, name) VALUES ('old', 'Old')")
    connection.executemany(
        "INSERT INTO narrative_messages(id, campaign_id, turn_number, sequence, kind, text) "
        "VALUES (?, 'old', 1, ?, ?, ?)",
        (("m0", 0, "player", "Hello there"), ("m1", 1, "spoken", "Well met.")),
    )
    connection.commit()
    connection.close()

    database = GameStateDatabase(path)
    assert database.initialize() == LATEST_SCHEMA_VERSION == 24
    with database.connect() as migrated:
        rows = migrated.execute(
            "SELECT id, kind, text, speaker_npc_id FROM narrative_messages ORDER BY sequence"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("m0", "player", "Hello there", None),
        ("m1", "spoken", "Well met.", None),
    ]
    backups = tuple((tmp_path / "backups" / "migrations").glob("pre-migration-v21-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 21


def test_people_dialogue_stores_speaker_and_projection_exposes_it(tmp_path: Path) -> None:
    database, service = _file_service(tmp_path)
    portrait_source = tmp_path / "merchant.png"
    portrait_source.write_bytes(b"\x89PNG\r\n\x1a\nmerchant")
    pending = service.visuals.stage_asset(
        campaign_id=DEMO_CAMPAIGN_ID,
        asset_kind="portrait",
        subject_type="character",
        subject_id=MERCHANT,
        source_path=portrait_source,
        signature="merchant-portrait",
        width=8,
        height=8,
    )
    portrait = service.visuals.confirm_asset(pending.id)

    service.resolve_npc_dialogue(MERCHANT, "Any news from the road?")

    with database.connect() as connection:
        speakers = {
            str(row["kind"]): row["speaker_npc_id"]
            for row in connection.execute(
                "SELECT kind, speaker_npc_id FROM narrative_messages "
                "WHERE id LIKE '%-player' OR id LIKE '%-spoken'"
            )
        }
    assert speakers["spoken"] == MERCHANT
    assert speakers["player"] is None
    spoken = service.load_active_dashboard().narrative.messages[-1]
    assert spoken.kind == "spoken"
    assert spoken.speaker_id == MERCHANT
    assert spoken.speaker_name == "Roadside Merchant"
    assert spoken.speaker_portrait == str(portrait.absolute_path)
    assert spoken.turn_number >= 0


class _FixedProvider:
    def __init__(self, result: ActionOutcome) -> None:
        self.result = result

    def resolve_action(self, *, action: str, context: dict[str, object]) -> ActionOutcome:
        return self.result


def test_turn_keeps_present_speaker_and_nulls_absent_or_unknown() -> None:
    database = GameStateDatabase.in_memory()
    database.initialize()
    seed_demo_campaign(database)
    service = GameStateService(database)
    outcome = ActionOutcome(
        narration="Voices rise along the road.",
        state_changes=(),
        quest_notes=(),
        suggested_actions=("Ask more", "Look around", "Wait", "Listen", "Leave", "Rest"),
        narrative_segments=(
            NarrativeSegment("narrative", "Voices rise along the road.", MERCHANT),
            NarrativeSegment("spoken", "Mind the ruts.", MERCHANT),
            NarrativeSegment("spoken", "The keep is closed.", "npc-lord-aric"),
            NarrativeSegment("spoken", "Boo.", "npc-ghost"),
        ),
    )

    service.resolve_player_action("I listen to the travellers", _FixedProvider(outcome))

    messages = service.load_active_dashboard().narrative.messages[-4:]
    assert [(m.kind, m.speaker_id, m.speaker_name) for m in messages] == [
        ("narrative", None, ""),
        ("spoken", MERCHANT, "Roadside Merchant"),
        ("spoken", None, ""),
        ("spoken", None, ""),
    ]
    with database.connect() as connection:
        stored = json.loads(
            connection.execute("SELECT response_segments_json FROM action_turns").fetchone()[0]
        )
    assert [segment["speaker_id"] for segment in stored] == [None, MERCHANT, None, None]


def test_turn_contract_accepts_optional_speaker_id_on_spoken_segments() -> None:
    segment_schema = TURN_RESPONSE_FORMAT["json_schema"]["schema"]["$defs"]["narrative_segment"]
    assert "speaker_id" in segment_schema["properties"]
    assert segment_schema["required"] == ["kind", "text"]
    payload = LocalModelActionResolver._payload(
        model="m", action="Wave", context={}, mode="json"
    )
    assert "the id of a present NPC who says this, or omit" in payload["messages"][0]["content"]

    content = json.dumps({
        "narrative_segments": [
            {"kind": "narrative", "text": "The road bends.", "speaker_id": MERCHANT},
            {"kind": "spoken", "text": "Over here!", "speaker_id": f" {MERCHANT} "},
            {"kind": "spoken", "text": "Who said that?"},
        ]
    })
    outcome = LocalModelActionResolver._parse(
        {"choices": [{"message": {"content": content}}]}
    )
    assert [segment.speaker_id for segment in outcome.narrative_segments] == [
        None, MERCHANT, None,
    ]
