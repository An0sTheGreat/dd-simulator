"""Repository interfaces for campaign metadata and selection."""

from __future__ import annotations

from uuid import uuid4

from dd_simulator.state.character_creation import plain_name
from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.errors import GameStateError
from dd_simulator.state.models import CampaignRecord


class CampaignRepository:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database

    @staticmethod
    def _record(row) -> CampaignRecord:  # type: ignore[no-untyped-def]
        return CampaignRecord(
            campaign_id=str(row["id"]),
            name=plain_name(str(row["name"])),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            creation_complete=bool(row["creation_complete"]),
            premise=str(row["premise"]),
        )

    def list_campaigns(self) -> tuple[CampaignRecord, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, name, status, created_at, updated_at, creation_complete, premise "
                "FROM campaigns ORDER BY updated_at DESC, id"
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def get(self, campaign_id: str) -> CampaignRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id, name, status, created_at, updated_at, creation_complete, premise "
                "FROM campaigns WHERE id = ?",
                (campaign_id,),
            ).fetchone()
        return None if row is None else self._record(row)

    def create(self, name: str, *, campaign_id: str | None = None) -> CampaignRecord:
        normalized = plain_name(name)
        if not normalized:
            raise ValueError("Campaign name cannot be blank")
        identifier = campaign_id or f"campaign-{uuid4().hex}"
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO campaigns(id, name, creation_complete) VALUES (?, ?, 0)",
                (identifier, normalized),
            )
        record = self.get(identifier)
        if record is None:  # pragma: no cover - defensive database invariant
            raise GameStateError("Created campaign could not be read back")
        return record

    def active_campaign_id(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'active_campaign_id'"
            ).fetchone()
        return None if row is None else str(row[0])

    def select(self, campaign_id: str) -> None:
        if self.get(campaign_id) is None:
            raise KeyError(f"Unknown campaign: {campaign_id}")
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO app_settings(key, value)
                VALUES ('active_campaign_id', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (campaign_id,),
            )

    def delete(self, campaign_id: str) -> str | None:
        """Delete one campaign and select the next completed campaign if needed."""

        with self.database.transaction() as connection:
            record = connection.execute(
                "SELECT name FROM campaigns WHERE id = ?", (campaign_id,)
            ).fetchone()
            if record is None:
                raise KeyError(f"Unknown campaign: {campaign_id}")
            active = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'active_campaign_id'"
            ).fetchone()
            connection.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
            if active is None or str(active[0]) != campaign_id:
                return None if active is None else str(active[0])
            replacement = connection.execute(
                "SELECT id FROM campaigns WHERE creation_complete = 1 "
                "ORDER BY updated_at DESC, id LIMIT 1"
            ).fetchone()
            if replacement is None:
                connection.execute(
                    "DELETE FROM app_settings WHERE key = 'active_campaign_id'"
                )
                return None
            replacement_id = str(replacement[0])
            connection.execute(
                "UPDATE app_settings SET value = ? WHERE key = 'active_campaign_id'",
                (replacement_id,),
            )
            return replacement_id
