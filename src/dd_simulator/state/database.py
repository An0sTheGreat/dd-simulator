"""Connection, migration, transaction, and integrity handling for SQLite."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from dd_simulator.state.errors import GameStateError
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION, apply_migrations


class GameStateDatabase:
    def __init__(self, path: Path | str, *, uri: bool = False) -> None:
        self.path = path if isinstance(path, str) else Path(path)
        self.uri = uri
        self._anchor: sqlite3.Connection | None = None

    @classmethod
    def in_memory(cls) -> "GameStateDatabase":
        target = f"file:dnd-simulator-{uuid4().hex}?mode=memory&cache=shared"
        database = cls(target, uri=True)
        database._anchor = database._new_connection()
        return database

    def _new_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=10.0,
            isolation_level=None,
            uri=self.uri,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        if not self.uri:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._new_connection()
            yield connection
        except sqlite3.Error as exc:
            raise GameStateError(f"Game-State Ledger error: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def initialize(self) -> int:
        with self.connect() as connection:
            existing = 0
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone() is not None:
                existing = int(connection.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
                ).fetchone()[0])
            if 0 < existing < LATEST_SCHEMA_VERSION and isinstance(self.path, Path):
                backup_dir = self.path.parent / "backups" / "migrations"
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                destination = backup_dir / f"pre-migration-v{existing}-{stamp}.db"
                suffix = 1
                while destination.exists():
                    destination = backup_dir / f"pre-migration-v{existing}-{stamp}-{suffix}.db"
                    suffix += 1
                with sqlite3.connect(destination) as target:
                    connection.backup(target)
            return apply_migrations(connection)

    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
        return int(row[0])

    def integrity_check(self) -> tuple[str, ...]:
        with self.connect() as connection:
            return tuple(
                str(row[0]) for row in connection.execute("PRAGMA integrity_check")
            )

    def close(self) -> None:
        if self._anchor is not None:
            self._anchor.close()
            self._anchor = None
