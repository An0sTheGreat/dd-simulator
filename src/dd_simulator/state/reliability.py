"""Named checkpoints, campaign repair, checksums, and audit-chain replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.errors import GameStateError
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class CampaignCheckpoint:
    id: str
    campaign_id: str
    label: str
    schema_version: int
    current_scene_id: str
    state_checksum: str
    visual_references: tuple[str, ...]
    backup_path: Path
    audit_sequence: int
    created_at: str


@dataclass(frozen=True, slots=True)
class RepairIssue:
    code: str
    description: str
    proposed_correction: str


@dataclass(frozen=True, slots=True)
class RepairResult:
    report_id: str
    status: str
    issues: tuple[RepairIssue, ...]
    corrections: tuple[str, ...]
    before_checksum: str
    after_checksum: str
    backup_path: Path | None


@dataclass(frozen=True, slots=True)
class ReplayResult:
    checkpoint_id: str
    valid: bool
    events_verified: int
    expected_checksum: str
    current_checksum: str
    message: str


_RELIABILITY_TABLES = {
    "campaign_checkpoints",
    "campaign_repair_reports",
    "campaign_state_audits",
}

# Parent-before-child order also serves the restore process.
_CAMPAIGN_FILTERS: tuple[tuple[str, str], ...] = (
    ("campaigns", "id = ?"),
    ("campaign_clock", "campaign_id = ?"),
    ("campaign_preferences", "campaign_id = ?"),
    ("locations", "campaign_id = ?"),
    ("characters", "campaign_id = ?"),
    ("character_attributes", "character_id IN (SELECT id FROM characters WHERE campaign_id = ?)"),
    ("character_resources", "character_id IN (SELECT id FROM characters WHERE campaign_id = ?)"),
    ("skills", "character_id IN (SELECT id FROM characters WHERE campaign_id = ?)"),
    ("abilities", "character_id IN (SELECT id FROM characters WHERE campaign_id = ?)"),
    ("status_effects", "character_id IN (SELECT id FROM characters WHERE campaign_id = ?)"),
    ("inventory_items", "character_id IN (SELECT id FROM characters WHERE campaign_id = ?)"),
    ("equipment_slots", "character_id IN (SELECT id FROM characters WHERE campaign_id = ?)"),
    ("quests", "campaign_id = ?"),
    ("quest_objectives", "quest_id IN (SELECT id FROM quests WHERE campaign_id = ?)"),
    ("quest_updates", "quest_id IN (SELECT id FROM quests WHERE campaign_id = ?)"),
    ("quest_rewards", "quest_id IN (SELECT id FROM quests WHERE campaign_id = ?)"),
    ("quest_reward_items", "reward_id IN (SELECT id FROM quest_rewards WHERE quest_id IN (SELECT id FROM quests WHERE campaign_id = ?))"),
    ("npcs", "campaign_id = ?"),
    ("merchant_stock", "npc_id IN (SELECT id FROM npcs WHERE campaign_id = ?)"),
    ("commerce_transactions", "campaign_id = ?"),
    ("crafting_recipes", "campaign_id = ?"),
    ("crafting_recipe_ingredients", "recipe_id IN (SELECT id FROM crafting_recipes WHERE campaign_id = ?)"),
    ("crafting_results", "campaign_id = ?"),
    ("relationships", "campaign_id = ?"),
    ("campaign_flags", "campaign_id = ?"),
    ("world_facts", "campaign_id = ?"),
    ("narratives", "campaign_id = ?"),
    ("events", "campaign_id = ?"),
    ("journal_entries", "campaign_id = ?"),
    ("faction_reputation", "campaign_id = ?"),
    ("action_turns", "campaign_id = ?"),
    ("narrative_messages", "campaign_id = ?"),
    ("travel_routes", "campaign_id = ?"),
    ("travel_history", "campaign_id = ?"),
    ("camp_history", "campaign_id = ?"),
    ("npc_conversations", "campaign_id = ?"),
    ("npc_memories", "campaign_id = ?"),
    ("combat_encounters", "campaign_id = ?"),
    ("combatants", "encounter_id IN (SELECT id FROM combat_encounters WHERE campaign_id = ?)"),
    ("combat_conditions", "combatant_id IN (SELECT id FROM combatants WHERE encounter_id IN (SELECT id FROM combat_encounters WHERE campaign_id = ?))"),
    ("combat_turns", "encounter_id IN (SELECT id FROM combat_encounters WHERE campaign_id = ?)"),
    ("combat_rewards", "encounter_id IN (SELECT id FROM combat_encounters WHERE campaign_id = ?)"),
    ("combat_reward_items", "reward_id IN (SELECT id FROM combat_rewards WHERE encounter_id IN (SELECT id FROM combat_encounters WHERE campaign_id = ?))"),
    ("visual_assets", "campaign_id = ?"),
    ("visual_asset_history", "campaign_id = ?"),
)


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    return value


def campaign_snapshot(connection: sqlite3.Connection, campaign_id: str) -> dict[str, list[dict[str, Any]]]:
    snapshot: dict[str, list[dict[str, Any]]] = {}
    available = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    for table, where_clause in _CAMPAIGN_FILTERS:
        if table not in available or table in _RELIABILITY_TABLES:
            continue
        rows = connection.execute(
            f'SELECT * FROM "{table}" WHERE {where_clause}',  # noqa: S608 - table list is static
            (campaign_id,),
        ).fetchall()
        normalized = [
            {key: _json_value(row[key]) for key in row.keys()}
            for row in rows
        ]
        normalized.sort(key=lambda value: json.dumps(value, sort_keys=True, default=str))
        snapshot[table] = normalized
    return snapshot


def campaign_checksum(connection: sqlite3.Connection, campaign_id: str) -> str:
    payload = json.dumps(
        campaign_snapshot(connection, campaign_id),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ReliabilityService:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database

    @property
    def backup_root(self) -> Path:
        if not isinstance(self.database.path, Path):
            raise GameStateError("Named checkpoints require a file-backed campaign ledger.")
        return self.database.path.parent / "backups"

    def checksum(self, campaign_id: str) -> str:
        with self.database.connect() as connection:
            self._require_campaign(connection, campaign_id)
            return campaign_checksum(connection, campaign_id)

    def list_checkpoints(self, campaign_id: str) -> tuple[CampaignCheckpoint, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM campaign_checkpoints WHERE campaign_id = ? "
                "ORDER BY created_at DESC, id DESC",
                (campaign_id,),
            ).fetchall()
        return tuple(self._checkpoint(row) for row in rows)

    def create_checkpoint(self, campaign_id: str, label: str) -> CampaignCheckpoint:
        normalized = " ".join(label.split())
        if not normalized:
            raise GameStateError("Enter a checkpoint name.")
        if len(normalized) > 80:
            raise GameStateError("Checkpoint names are limited to 80 characters.")
        checkpoint_id = f"checkpoint-{uuid4().hex}"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        relative = Path("checkpoints", f"{stamp}-{checkpoint_id[-12:]}.db")
        destination = self._safe_backup_path(relative)
        with self.database.transaction() as connection:
            self._require_campaign(connection, campaign_id)
            checksum = campaign_checksum(connection, campaign_id)
            scene = connection.execute(
                "SELECT id FROM locations WHERE campaign_id = ? AND is_current = 1",
                (campaign_id,),
            ).fetchone()
            visual_rows = connection.execute(
                "SELECT relative_path FROM visual_assets WHERE campaign_id = ? "
                "AND status = 'confirmed' AND (canonical = 1 OR active = 1)",
                (campaign_id,),
            ).fetchall()
            audit_sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM campaign_state_audits "
                    "WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()[0]
            )
            connection.execute(
                "INSERT INTO campaign_checkpoints(id, campaign_id, label, schema_version, "
                "current_scene_id, state_checksum, visual_references_json, "
                "backup_relative_path, audit_sequence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    checkpoint_id,
                    campaign_id,
                    normalized,
                    LATEST_SCHEMA_VERSION,
                    "" if scene is None else str(scene["id"]),
                    checksum,
                    json.dumps([str(row["relative_path"]) for row in visual_rows]),
                    relative.as_posix(),
                    audit_sequence,
                ),
            )
        try:
            self._backup_database(destination)
        except Exception:
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM campaign_checkpoints WHERE id = ?", (checkpoint_id,))
            raise
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM campaign_checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()
        return self._checkpoint(row)

    def load_checkpoint(self, checkpoint_id: str) -> CampaignCheckpoint:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM campaign_checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()
            if row is None:
                raise GameStateError("That checkpoint no longer exists.")
            checkpoint = self._checkpoint(row)
            reliability_rows = {
                table: [dict(value) for value in connection.execute(
                    f'SELECT * FROM "{table}" WHERE campaign_id = ?',  # noqa: S608
                    (checkpoint.campaign_id,),
                ).fetchall()]
                for table in _RELIABILITY_TABLES
            }
            before_checksum = campaign_checksum(connection, checkpoint.campaign_id)
        self._validate_checkpoint_file(checkpoint)
        recovery_relative = Path(
            "recovery",
            f"before-load-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}.db",
        )
        self._backup_database(self._safe_backup_path(recovery_relative))

        with self.database.connect() as connection:
            connection.execute("ATTACH DATABASE ? AS checkpoint", (str(checkpoint.backup_path),))
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM campaigns WHERE id = ?", (checkpoint.campaign_id,))
                connection.execute("PRAGMA defer_foreign_keys = ON")
                for table, where_clause in _CAMPAIGN_FILTERS:
                    columns = [
                        str(info[1])
                        for info in connection.execute(f'PRAGMA main.table_info("{table}")')
                    ]
                    if not columns:
                        continue
                    quoted = ", ".join(f'"{column}"' for column in columns)
                    source_where = where_clause.replace(
                        "FROM ", "FROM checkpoint."
                    )
                    if table == "inventory_items":
                        source_rows = connection.execute(
                            f'SELECT {quoted} FROM checkpoint."{table}" WHERE {source_where}',  # noqa: S608
                            (checkpoint.campaign_id,),
                        ).fetchall()
                        position_index = columns.index("inventory_position")
                        placeholders = ", ".join("?" for _ in columns)
                        restore_null_ids: list[str] = []
                        for index, source_row in enumerate(source_rows):
                            values = [source_row[column] for column in columns]
                            if values[position_index] is None:
                                restore_null_ids.append(str(source_row["id"]))
                                values[position_index] = 100000 + index
                            connection.execute(
                                f'INSERT INTO main."{table}" ({quoted}) VALUES ({placeholders})',  # noqa: S608
                                values,
                            )
                        for item_id in restore_null_ids:
                            connection.execute(
                                "UPDATE inventory_items SET inventory_position = NULL WHERE id = ?",
                                (item_id,),
                            )
                        continue
                    connection.execute(
                        f'INSERT INTO main."{table}" ({quoted}) '
                        f'SELECT {quoted} FROM checkpoint."{table}" WHERE {source_where}',  # noqa: S608
                        (checkpoint.campaign_id,),
                    )
                for table, rows in reliability_rows.items():
                    for saved in rows:
                        columns = tuple(saved)
                        quoted = ", ".join(f'"{column}"' for column in columns)
                        placeholders = ", ".join("?" for _ in columns)
                        connection.execute(
                            f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({placeholders})',  # noqa: S608
                            tuple(saved[column] for column in columns),
                        )
                connection.execute(
                    "INSERT INTO app_settings(key, value) VALUES ('active_campaign_id', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (checkpoint.campaign_id,),
                )
                restored_checksum = campaign_checksum(connection, checkpoint.campaign_id)
                if restored_checksum != checkpoint.state_checksum:
                    raise GameStateError(
                        "Checkpoint contents did not match their stored checksum; load was rolled back."
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.execute("DETACH DATABASE checkpoint")
        self.record_audit(
            checkpoint.campaign_id,
            "checkpoint_load",
            f"Loaded checkpoint {checkpoint.label}.",
            {"checkpoint_id": checkpoint.id},
            before_checksum=before_checksum,
        )
        return checkpoint

    def inspect_repair(self, campaign_id: str) -> tuple[RepairIssue, ...]:
        issues: list[RepairIssue] = []
        integrity = self.database.integrity_check()
        if integrity != ("ok",):
            issues.append(RepairIssue(
                "database_integrity",
                "; ".join(integrity),
                "Restore a verified checkpoint; automatic repair will not rewrite corrupt pages.",
            ))
        with self.database.connect() as connection:
            self._require_campaign(connection, campaign_id)
            player_count = int(connection.execute(
                "SELECT COUNT(*) FROM characters WHERE campaign_id = ? AND is_player = 1",
                (campaign_id,),
            ).fetchone()[0])
            if player_count != 1:
                issues.append(RepairIssue(
                    "player_count", f"Expected one player character; found {player_count}.",
                    "No automatic correction; load a verified checkpoint.",
                ))
            current_count = int(connection.execute(
                "SELECT COUNT(*) FROM locations WHERE campaign_id = ? AND is_current = 1",
                (campaign_id,),
            ).fetchone()[0])
            if current_count == 0:
                issues.append(RepairIssue(
                    "missing_current_location", "No current location is selected.",
                    "Select the most recently visited discovered location.",
                ))
            current_hidden = connection.execute(
                "SELECT id FROM locations WHERE campaign_id = ? AND is_current = 1 "
                "AND (discovered = 0 OR visit_count < 1)",
                (campaign_id,),
            ).fetchall()
            if current_hidden:
                issues.append(RepairIssue(
                    "current_location_hidden",
                    "The current location is not marked discovered and visited.",
                    "Mark the current location discovered with at least one visit.",
                ))
            undersized = connection.execute(
                "SELECT characters.id FROM characters WHERE campaign_id = ? AND "
                "inventory_capacity < MAX(320, COALESCE((SELECT MAX(inventory_position) + 1 "
                "FROM inventory_items WHERE character_id = characters.id), 0))",
                (campaign_id,),
            ).fetchall()
            if undersized:
                issues.append(RepairIssue(
                    "inventory_capacity", "Inventory capacity is below its occupied slot range.",
                    "Expand capacity to the paged inventory reserve and beyond the final occupied slot.",
                ))
            visible_equipped = connection.execute(
                "SELECT inventory_items.id FROM inventory_items JOIN equipment_slots "
                "ON equipment_slots.inventory_item_id = inventory_items.id "
                "JOIN characters ON characters.id = inventory_items.character_id "
                "WHERE characters.campaign_id = ? AND inventory_items.inventory_position IS NOT NULL",
                (campaign_id,),
            ).fetchall()
            if visible_equipped:
                issues.append(RepairIssue(
                    "equipped_in_inventory", "Equipped items are also occupying bag positions.",
                    "Remove equipped items from bag positions.",
                ))
            missing_visuals = []
            for row in connection.execute(
                "SELECT id, relative_path FROM visual_assets WHERE campaign_id = ? "
                "AND status = 'confirmed'",
                (campaign_id,),
            ).fetchall():
                candidate = self.database.path.parent / "visual_assets" / str(row["relative_path"])  # type: ignore[union-attr]
                if not candidate.is_file():
                    missing_visuals.append(str(row["id"]))
            if missing_visuals:
                issues.append(RepairIssue(
                    "missing_visuals",
                    f"{len(missing_visuals)} confirmed visual file(s) are missing.",
                    "Mark missing visuals unavailable so the themed placeholder is used.",
                ))
        return tuple(issues)

    def apply_repair(self, campaign_id: str) -> RepairResult:
        issues = self.inspect_repair(campaign_id)
        before = self.checksum(campaign_id)
        report_id = f"repair-{uuid4().hex}"
        if not issues:
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO campaign_repair_reports(id, campaign_id, status, "
                    "discrepancies_json, corrections_json, before_checksum, after_checksum) "
                    "VALUES (?, ?, 'clean', '[]', '[]', ?, ?)",
                    (report_id, campaign_id, before, before),
                )
            return RepairResult(report_id, "clean", (), (), before, before, None)
        unsafe = {"database_integrity", "player_count"}
        if any(issue.code in unsafe for issue in issues):
            raise GameStateError(
                "Automatic repair stopped because the ledger requires checkpoint restoration."
            )
        relative = Path(
            "repairs",
            f"before-repair-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{report_id[-8:]}.db",
        )
        backup = self._safe_backup_path(relative)
        self._backup_database(backup)
        corrections: list[str] = []
        with self.database.transaction() as connection:
            codes = {issue.code for issue in issues}
            if "missing_current_location" in codes:
                candidate = connection.execute(
                    "SELECT id FROM locations WHERE campaign_id = ? "
                    "ORDER BY visit_count DESC, last_visited_at DESC, discovered DESC, id LIMIT 1",
                    (campaign_id,),
                ).fetchone()
                if candidate is None:
                    raise GameStateError("No location exists to repair the current scene.")
                connection.execute("UPDATE locations SET is_current = 0 WHERE campaign_id = ?", (campaign_id,))
                connection.execute("UPDATE locations SET is_current = 1 WHERE id = ?", (candidate["id"],))
                corrections.append("Selected the most recently visited location as current.")
            if "current_location_hidden" in codes or "missing_current_location" in codes:
                connection.execute(
                    "UPDATE locations SET discovered = 1, visit_count = MAX(visit_count, 1), "
                    "first_discovered_at = COALESCE(first_discovered_at, CURRENT_TIMESTAMP), "
                    "last_visited_at = COALESCE(last_visited_at, CURRENT_TIMESTAMP) "
                    "WHERE campaign_id = ? AND is_current = 1",
                    (campaign_id,),
                )
                corrections.append("Marked the current location discovered and visited.")
            if "inventory_capacity" in codes:
                connection.execute(
                    "UPDATE characters SET inventory_capacity = MAX(320, COALESCE((SELECT "
                    "MAX(inventory_position) + 1 FROM inventory_items WHERE character_id = characters.id), 0)) "
                    "WHERE campaign_id = ?",
                    (campaign_id,),
                )
                corrections.append("Expanded invalid inventory capacity values.")
            if "equipped_in_inventory" in codes:
                connection.execute(
                    "UPDATE inventory_items SET inventory_position = NULL WHERE id IN "
                    "(SELECT equipment_slots.inventory_item_id FROM equipment_slots JOIN characters "
                    "ON characters.id = equipment_slots.character_id WHERE characters.campaign_id = ? "
                    "AND equipment_slots.inventory_item_id IS NOT NULL)",
                    (campaign_id,),
                )
                corrections.append("Removed equipped items from bag positions.")
            if "missing_visuals" in codes:
                rows = connection.execute(
                    "SELECT id, relative_path FROM visual_assets WHERE campaign_id = ? AND status = 'confirmed'",
                    (campaign_id,),
                ).fetchall()
                for row in rows:
                    candidate = self.database.path.parent / "visual_assets" / str(row["relative_path"])  # type: ignore[union-attr]
                    if not candidate.is_file():
                        connection.execute(
                            "UPDATE visual_assets SET status = 'missing', canonical = 0, active = 0 WHERE id = ?",
                            (row["id"],),
                        )
                corrections.append("Marked unavailable visual files missing.")
            after = campaign_checksum(connection, campaign_id)
            connection.execute(
                "INSERT INTO campaign_repair_reports(id, campaign_id, status, discrepancies_json, "
                "corrections_json, before_checksum, after_checksum, backup_relative_path, applied_at) "
                "VALUES (?, ?, 'applied', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    report_id,
                    campaign_id,
                    json.dumps([asdict(issue) for issue in issues]),
                    json.dumps(corrections),
                    before,
                    after,
                    relative.as_posix(),
                ),
            )
        self.record_audit(
            campaign_id,
            "repair",
            "Applied safe campaign repairs.",
            {"report_id": report_id, "corrections": corrections},
            before_checksum=before,
        )
        return RepairResult(report_id, "applied", issues, tuple(corrections), before, after, backup)

    def record_audit(
        self,
        campaign_id: str,
        event_type: str,
        summary: str,
        operation: Mapping[str, Any],
        *,
        before_checksum: str,
    ) -> None:
        with self.database.transaction() as connection:
            after = campaign_checksum(connection, campaign_id)
            sequence = int(connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM campaign_state_audits WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0])
            connection.execute(
                "INSERT INTO campaign_state_audits(id, campaign_id, sequence, event_type, "
                "summary, operation_json, before_checksum, after_checksum) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"audit-{uuid4().hex}", campaign_id, sequence, event_type,
                    summary[:500], json.dumps(dict(operation), sort_keys=True, default=str),
                    before_checksum, after,
                ),
            )

    def verify_replay(self, checkpoint_id: str) -> ReplayResult:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM campaign_checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()
            if row is None:
                raise GameStateError("That checkpoint no longer exists.")
            checkpoint = self._checkpoint(row)
            events = connection.execute(
                "SELECT * FROM campaign_state_audits WHERE campaign_id = ? AND sequence > ? "
                "ORDER BY sequence",
                (checkpoint.campaign_id, checkpoint.audit_sequence),
            ).fetchall()
            expected = checkpoint.state_checksum
            for event in events:
                if str(event["before_checksum"]) != expected:
                    return ReplayResult(
                        checkpoint.id, False, 0, expected,
                        campaign_checksum(connection, checkpoint.campaign_id),
                        f"Audit chain breaks before event {event['sequence']} ({event['event_type']}).",
                    )
                expected = str(event["after_checksum"])
            current = campaign_checksum(connection, checkpoint.campaign_id)
        valid = expected == current
        message = (
            f"Replay checksum verified across {len(events)} audited event(s)."
            if valid
            else "Current campaign state differs from the audited replay checksum."
        )
        return ReplayResult(checkpoint.id, valid, len(events), expected, current, message)

    def _checkpoint(self, row: sqlite3.Row) -> CampaignCheckpoint:
        return CampaignCheckpoint(
            id=str(row["id"]),
            campaign_id=str(row["campaign_id"]),
            label=str(row["label"]),
            schema_version=int(row["schema_version"]),
            current_scene_id=str(row["current_scene_id"]),
            state_checksum=str(row["state_checksum"]),
            visual_references=tuple(json.loads(str(row["visual_references_json"]))),
            backup_path=self._safe_backup_path(Path(str(row["backup_relative_path"]))),
            audit_sequence=int(row["audit_sequence"]),
            created_at=str(row["created_at"]),
        )

    def _safe_backup_path(self, relative: Path) -> Path:
        root = self.backup_root.resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise GameStateError("Checkpoint path escaped the backup directory.") from exc
        return candidate

    def _backup_database(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.database.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)

    def _validate_checkpoint_file(self, checkpoint: CampaignCheckpoint) -> None:
        if not checkpoint.backup_path.is_file():
            raise GameStateError("The checkpoint backup file is missing.")
        with sqlite3.connect(checkpoint.backup_path) as connection:
            integrity = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check"))
            if integrity != ("ok",):
                raise GameStateError("The checkpoint backup failed SQLite integrity validation.")
            version = int(connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0])
            if version != LATEST_SCHEMA_VERSION or checkpoint.schema_version != LATEST_SCHEMA_VERSION:
                raise GameStateError(
                    f"Checkpoint schema {version} is not compatible with application schema "
                    f"{LATEST_SCHEMA_VERSION}."
                )
            row = connection.execute(
                "SELECT state_checksum FROM campaign_checkpoints WHERE id = ?",
                (checkpoint.id,),
            ).fetchone()
            if row is None or str(row[0]) != checkpoint.state_checksum:
                raise GameStateError("Checkpoint metadata is missing or does not match its backup.")

    @staticmethod
    def _require_campaign(connection: sqlite3.Connection, campaign_id: str) -> None:
        if connection.execute("SELECT 1 FROM campaigns WHERE id = ?", (campaign_id,)).fetchone() is None:
            raise GameStateError(f"Unknown campaign: {campaign_id}")
