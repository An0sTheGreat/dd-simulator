"""Persistent Visual Registry for state-matched campaign artwork."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.errors import GameStateError


_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")
_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass(frozen=True, slots=True)
class VisualAssetRecord:
    id: str
    campaign_id: str
    asset_kind: str
    subject_type: str
    subject_id: str
    state_signature: str
    version: int
    asset_role: str
    relative_path: str
    absolute_path: Path | None
    content_hash: str
    mime_type: str
    width: int
    height: int
    status: str
    canonical: bool
    active: bool
    source: str
    prompt_summary: str
    negative_prompt: str
    generation_seed: str
    reference_asset_ids: tuple[str, ...]
    attachment_references: tuple[str, ...]
    art_style: str
    camera_style: str
    lighting_style: str
    appearance_lock: Mapping[str, Any]
    use_count: int
    created_at: str
    confirmed_at: str
    last_used_at: str


@dataclass(frozen=True, slots=True)
class VisualHistoryRecord:
    id: str
    asset_id: str
    action: str
    state_signature: str
    detail: str
    created_at: str


def state_signature(values: Mapping[str, Any]) -> str:
    """Return a stable signature for the visual facts that define an image state."""

    normalized = {
        str(key): "" if value is None else str(value).strip()
        for key, value in sorted(values.items())
    }
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _field(row: sqlite3.Row | Mapping[str, Any], key: str, default: Any = "") -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def character_state_signature(
    row: sqlite3.Row | Mapping[str, Any],
    *,
    equipment: tuple[str, ...] = (),
    art_style: str = "",
    camera_style: str = "",
) -> str:
    return state_signature(
        {
            "name": _field(row, "name"),
            "species": _field(row, "species"),
            "class": _field(row, "character_class"),
            "body": _field(row, "body_description"),
            "face": _field(row, "face_description"),
            "clothing": _field(row, "clothing_style"),
            "equipment": "|".join(sorted(equipment)),
            "art_style": art_style,
            "camera_style": camera_style,
        }
    )


def _time_state(time_label: str) -> str:
    lowered = time_label.casefold()
    for state, words in (
        ("night", ("night", "midnight")),
        ("evening", ("evening", "dusk", "sunset")),
        ("morning", ("morning", "dawn", "sunrise")),
        ("day", ("afternoon", "noon", "day")),
    ):
        if any(word in lowered for word in words):
            return state
    return "unspecified"


def _weather_state(weather: str) -> str:
    lowered = weather.casefold()
    for state, words in (
        ("storm", ("storm", "thunder", "hurricane")),
        ("winter", ("blizzard", "snow", "winter", "ice")),
        ("flood", ("flood", "deluge")),
        ("fire", ("wildfire", "ashfall", "burning")),
        ("fog", ("dense fog", "magical fog")),
    ):
        if any(word in lowered for word in words):
            return state
    return "ordinary"


def location_state_signature(
    row: sqlite3.Row | Mapping[str, Any],
    *,
    time_label: str = "",
    art_style: str = "",
    camera_style: str = "",
) -> str:
    return state_signature(
        {
            "name": _field(row, "name"),
            "region": _field(row, "region"),
            "biome": _field(row, "biome"),
            "structural_condition": _field(row, "description"),
            "weather_state": _weather_state(str(_field(row, "weather"))),
            "danger": _field(row, "danger"),
            "route": _field(row, "route_status"),
            "time_state": _time_state(time_label),
            "art_style": art_style,
            "camera_style": camera_style,
        }
    )


def _safe_component(value: str) -> str:
    cleaned = _SAFE_COMPONENT.sub("-", value.strip()).strip(".-")
    return cleaned or "unknown"


def _absolute_asset_path(assets_root: Path | None, relative_path: str) -> Path | None:
    if assets_root is None or not relative_path:
        return None
    root = assets_root.resolve()
    candidate = (root / Path(relative_path)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _record_from_row(
    row: sqlite3.Row,
    assets_root: Path | None,
) -> VisualAssetRecord:
    path = _absolute_asset_path(assets_root, str(row["relative_path"]))
    status = str(row["status"])
    if status == "confirmed" and (path is None or not path.is_file()):
        status = "missing"
    return VisualAssetRecord(
        id=str(row["id"]),
        campaign_id=str(row["campaign_id"]),
        asset_kind=str(row["asset_kind"]),
        subject_type=str(row["subject_type"]),
        subject_id=str(row["subject_id"]),
        state_signature=str(row["state_signature"]),
        version=int(row["version"]),
        asset_role=str(row["asset_role"]),
        relative_path=str(row["relative_path"]),
        absolute_path=path,
        content_hash=str(row["content_hash"]),
        mime_type=str(row["mime_type"]),
        width=int(row["width"]),
        height=int(row["height"]),
        status=status,
        canonical=bool(row["canonical"]),
        active=bool(row["active"]),
        source=str(row["source"]),
        prompt_summary=str(row["prompt_summary"]),
        negative_prompt=str(row["negative_prompt"]),
        generation_seed=str(row["generation_seed"]),
        reference_asset_ids=tuple(json.loads(str(row["reference_asset_ids_json"]))),
        attachment_references=tuple(
            json.loads(str(row["attachment_references_json"]))
        ),
        art_style=str(row["art_style"]),
        camera_style=str(row["camera_style"]),
        lighting_style=str(row["lighting_style"]),
        appearance_lock=json.loads(str(row["appearance_lock_json"])),
        use_count=int(row["use_count"]),
        created_at=str(row["created_at"]),
        confirmed_at="" if row["confirmed_at"] is None else str(row["confirmed_at"]),
        last_used_at="" if row["last_used_at"] is None else str(row["last_used_at"]),
    )


def resolve_visual_record(
    connection: sqlite3.Connection,
    assets_root: Path | None,
    *,
    campaign_id: str,
    asset_kind: str,
    subject_type: str,
    subject_id: str,
    signature: str,
) -> VisualAssetRecord | None:
    """Resolve exact confirmed/pending state first, then a confirmed canonical fallback."""

    exact_rows = connection.execute(
        """
        SELECT * FROM visual_assets
        WHERE campaign_id = ? AND asset_kind = ? AND subject_type = ?
          AND subject_id = ? AND status = 'confirmed'
          AND state_signature = ?
        ORDER BY version DESC, created_at DESC
        """,
        (campaign_id, asset_kind, subject_type, subject_id, signature),
    ).fetchall()
    exact_missing: VisualAssetRecord | None = None
    for row in exact_rows:
        record = _record_from_row(row, assets_root)
        if record.status == "confirmed":
            return record
        if exact_missing is None:
            exact_missing = record
    pending = connection.execute(
        """
        SELECT * FROM visual_assets
        WHERE campaign_id = ? AND asset_kind = ? AND subject_type = ?
          AND subject_id = ? AND state_signature = ? AND status = 'pending'
        ORDER BY version DESC, created_at DESC LIMIT 1
        """,
        (campaign_id, asset_kind, subject_type, subject_id, signature),
    ).fetchone()
    if pending is not None:
        return _record_from_row(pending, assets_root)
    if exact_missing is not None:
        return exact_missing
    canonical_rows = connection.execute(
        """
        SELECT * FROM visual_assets
        WHERE campaign_id = ? AND asset_kind = ? AND subject_type = ?
          AND subject_id = ? AND status = 'confirmed' AND canonical = 1
        ORDER BY version DESC, created_at DESC
        """,
        (campaign_id, asset_kind, subject_type, subject_id),
    ).fetchall()
    canonical_missing: VisualAssetRecord | None = None
    for row in canonical_rows:
        record = _record_from_row(row, assets_root)
        if record.status == "confirmed":
            return record
        if canonical_missing is None:
            canonical_missing = record
    return canonical_missing


class VisualRegistryService:
    """Stage, confirm, version, resolve, and audit local visual assets."""

    def __init__(
        self,
        database: GameStateDatabase,
        assets_root: Path | None = None,
    ) -> None:
        self.database = database
        if assets_root is not None:
            self.assets_root = Path(assets_root)
        elif isinstance(database.path, Path):
            self.assets_root = database.path.parent / "visual_assets"
        else:
            self.assets_root = None

    def initialize_storage(self) -> None:
        """Create the registry root for file-backed campaigns."""

        if self.assets_root is not None:
            self.assets_root.mkdir(parents=True, exist_ok=True)

    def current_state_signature(
        self,
        campaign_id: str,
        subject_type: str,
        subject_id: str,
    ) -> str:
        with self.database.connect() as connection:
            preferences = connection.execute(
                "SELECT visual_style, camera_style FROM campaign_preferences "
                "WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            art_style = "" if preferences is None else str(preferences["visual_style"])
            camera_style = "" if preferences is None else str(preferences["camera_style"])
            if subject_type == "character":
                row = connection.execute(
                    "SELECT * FROM characters WHERE id = ? AND campaign_id = ?",
                    (subject_id, campaign_id),
                ).fetchone()
                if row is None:
                    raise GameStateError(f"Unknown visual character subject: {subject_id}")
                equipment = tuple(
                    str(item["name"])
                    for item in connection.execute(
                        """
                        SELECT inventory_items.name
                        FROM equipment_slots
                        JOIN inventory_items
                          ON inventory_items.id = equipment_slots.inventory_item_id
                        WHERE equipment_slots.character_id = ?
                        ORDER BY equipment_slots.slot_index
                        """,
                        (subject_id,),
                    ).fetchall()
                )
                return character_state_signature(
                    row,
                    equipment=equipment,
                    art_style=art_style,
                    camera_style=camera_style,
                )
            if subject_type == "location":
                row = connection.execute(
                    "SELECT * FROM locations WHERE id = ? AND campaign_id = ?",
                    (subject_id, campaign_id),
                ).fetchone()
                if row is None:
                    raise GameStateError(f"Unknown visual location subject: {subject_id}")
                clock = connection.execute(
                    "SELECT time_label FROM campaign_clock WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()
                return location_state_signature(
                    row,
                    time_label="" if clock is None else str(clock["time_label"]),
                    art_style=art_style,
                    camera_style=camera_style,
                )
        raise GameStateError(f"Unsupported visual subject type: {subject_type}")

    def stage_asset(
        self,
        *,
        campaign_id: str,
        asset_kind: str,
        subject_type: str,
        subject_id: str,
        source_path: Path,
        signature: str | None = None,
        asset_role: str | None = None,
        source: str = "local",
        prompt_summary: str = "",
        negative_prompt: str = "",
        generation_seed: str = "",
        reference_asset_ids: tuple[str, ...] = (),
        attachment_references: tuple[str, ...] = (),
        art_style: str = "",
        camera_style: str = "",
        lighting_style: str = "",
        appearance_lock: Mapping[str, Any] | None = None,
        width: int = 0,
        height: int = 0,
    ) -> VisualAssetRecord:
        expected_subjects = {
            "portrait": "character",
            "location": "location",
            "item": "item",
            "scene": "scene",
        }
        if expected_subjects.get(asset_kind) != subject_type:
            raise GameStateError("Visual kind and subject type are incompatible")
        if self.assets_root is None:
            raise GameStateError("Visual assets require a file-backed campaign database")
        source_path = Path(source_path).resolve()
        suffix = source_path.suffix.casefold()
        if not source_path.is_file() or suffix not in _MIME_TYPES:
            raise GameStateError("Visual asset must be an existing PNG, JPEG, or WebP file")
        content = source_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        if signature is None:
            if subject_type not in {"character", "location"}:
                raise GameStateError(
                    "Item and scene visuals require an explicit state signature"
                )
            signature = self.current_state_signature(campaign_id, subject_type, subject_id)

        with self.database.connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM visual_assets
                WHERE campaign_id = ? AND asset_kind = ? AND subject_type = ?
                  AND subject_id = ? AND state_signature = ? AND content_hash = ?
                  AND status IN ('pending', 'confirmed')
                ORDER BY version DESC LIMIT 1
                """,
                (
                    campaign_id, asset_kind, subject_type, subject_id,
                    signature, content_hash,
                ),
            ).fetchone()
        if existing is not None:
            with self.database.transaction() as connection:
                self._append_history(
                    connection, str(existing["id"]), campaign_id, "reused", signature,
                    "Identical content reused for the same visual state.",
                )
            return _record_from_row(existing, self.assets_root)

        with self.database.connect() as connection:
            preferences = connection.execute(
                "SELECT visual_style, camera_style FROM campaign_preferences "
                "WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if not art_style and preferences is not None:
                art_style = str(preferences["visual_style"])
            if not camera_style and preferences is not None:
                camera_style = str(preferences["camera_style"])
            if asset_role is None:
                if asset_kind == "portrait":
                    has_canonical = connection.execute(
                        """
                        SELECT 1 FROM visual_assets
                        WHERE campaign_id = ? AND asset_kind = 'portrait'
                          AND subject_type = ? AND subject_id = ?
                          AND canonical = 1 AND status = 'confirmed'
                        LIMIT 1
                        """,
                        (campaign_id, subject_type, subject_id),
                    ).fetchone()
                    asset_role = "active" if has_canonical is not None else "canonical"
                else:
                    asset_role = "state"
            if asset_role not in {"canonical", "active", "state", "history"}:
                raise GameStateError(f"Unsupported visual asset role: {asset_role}")
            version_row = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM visual_assets
                WHERE campaign_id = ? AND asset_kind = ? AND subject_type = ?
                  AND subject_id = ? AND state_signature = ?
                """,
                (campaign_id, asset_kind, subject_type, subject_id, signature),
            ).fetchone()
        version = int(version_row[0])
        asset_id = f"visual-{uuid4().hex}"
        relative = Path(
            _safe_component(campaign_id),
            asset_kind,
            _safe_component(subject_id),
            f"v{version}-{content_hash[:12]}{suffix}",
        )
        destination = (self.assets_root / relative).resolve()
        root = self.assets_root.resolve()
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise GameStateError("Visual destination escaped the registry root") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination != source_path:
            shutil.copy2(source_path, destination)

        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO visual_assets(
                        id, campaign_id, asset_kind, subject_type, subject_id,
                        state_signature, version, asset_role, relative_path,
                        content_hash, mime_type, width, height, status, canonical,
                        active, source, prompt_summary, negative_prompt,
                        generation_seed, reference_asset_ids_json,
                        attachment_references_json, art_style, camera_style,
                        lighting_style, appearance_lock_json
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, 0,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        asset_id, campaign_id, asset_kind, subject_type, subject_id,
                        signature, version, asset_role, relative.as_posix(), content_hash,
                        _MIME_TYPES[suffix], max(0, width), max(0, height),
                        source.strip() or "local", prompt_summary.strip(),
                        negative_prompt.strip(), generation_seed.strip(),
                        json.dumps(reference_asset_ids),
                        json.dumps(attachment_references), art_style.strip(),
                        camera_style.strip(), lighting_style.strip(),
                        json.dumps(appearance_lock or {}, sort_keys=True),
                    ),
                )
                self._append_history(
                    connection, asset_id, campaign_id, "staged", signature,
                    "Visual staged and awaiting confirmation.",
                )
                row = connection.execute(
                    "SELECT * FROM visual_assets WHERE id = ?", (asset_id,)
                ).fetchone()
        except Exception:
            if destination != source_path and destination.is_file():
                destination.unlink()
            raise
        return _record_from_row(row, self.assets_root)

    def confirm_asset(self, asset_id: str) -> VisualAssetRecord:
        with self.database.connect() as connection:
            candidate = connection.execute(
                "SELECT * FROM visual_assets WHERE id = ?", (asset_id,)
            ).fetchone()
        if candidate is None:
            raise GameStateError(f"Unknown visual asset: {asset_id}")
        path = _absolute_asset_path(self.assets_root, str(candidate["relative_path"]))
        if path is None or not path.is_file():
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE visual_assets SET status = 'missing', canonical = 0, active = 0 WHERE id = ?",
                    (asset_id,),
                )
                self._append_history(
                    connection, asset_id, str(candidate["campaign_id"]), "missing",
                    str(candidate["state_signature"]),
                    "Asset file was missing at confirmation.",
                )
            raise GameStateError("Visual asset file is missing")

        with self.database.transaction() as connection:
            asset = connection.execute(
                "SELECT * FROM visual_assets WHERE id = ?", (asset_id,)
            ).fetchone()
            if str(asset["status"]) not in {"pending", "confirmed"}:
                raise GameStateError("Only pending or confirmed visuals can be confirmed")

            asset_role = str(asset["asset_role"])
            is_portrait_active = (
                str(asset["asset_kind"]) == "portrait" and asset_role != "canonical"
            )
            previous = connection.execute(
                """
                SELECT id FROM visual_assets
                WHERE campaign_id = ? AND asset_kind = ? AND subject_type = ?
                  AND subject_id = ? AND state_signature = ?
                  AND status = 'confirmed' AND id <> ?
                  AND (? = 0 OR canonical = 0)
                """,
                (
                    asset["campaign_id"], asset["asset_kind"], asset["subject_type"],
                    asset["subject_id"], asset["state_signature"], asset_id,
                    1 if is_portrait_active else 0,
                ),
            ).fetchall()
            for row in previous:
                connection.execute(
                    "UPDATE visual_assets SET status = 'superseded', canonical = 0, active = 0 WHERE id = ?",
                    (row["id"],),
                )
                self._append_history(
                    connection, str(row["id"]), str(asset["campaign_id"]),
                    "superseded", str(asset["state_signature"]),
                    f"Superseded by {asset_id}.",
                )
            connection.execute(
                """
                UPDATE visual_assets SET active = 0
                WHERE campaign_id = ? AND asset_kind = ? AND subject_type = ?
                  AND subject_id = ? AND id <> ?
                """,
                (
                    asset["campaign_id"], asset["asset_kind"], asset["subject_type"],
                    asset["subject_id"], asset_id,
                ),
            )
            new_canonical = 0
            if not is_portrait_active:
                connection.execute(
                    """
                    UPDATE visual_assets SET canonical = 0
                    WHERE campaign_id = ? AND asset_kind = ? AND subject_type = ?
                      AND subject_id = ? AND id <> ?
                    """,
                    (
                        asset["campaign_id"], asset["asset_kind"], asset["subject_type"],
                        asset["subject_id"], asset_id,
                    ),
                )
                new_canonical = 1
            connection.execute(
                """
                UPDATE visual_assets
                SET status = 'confirmed', canonical = ?, active = 1,
                    confirmed_at = COALESCE(confirmed_at, CURRENT_TIMESTAMP)
                WHERE id = ?
                """,
                (new_canonical, asset_id),
            )
            role_detail = "canonical" if new_canonical else "active-state"
            self._append_history(
                connection, asset_id, str(asset["campaign_id"]), "confirmed",
                str(asset["state_signature"]), f"Visual confirmed as {role_detail}.",
            )
            result = connection.execute(
                "SELECT * FROM visual_assets WHERE id = ?", (asset_id,)
            ).fetchone()
        return _record_from_row(result, self.assets_root)

    def reject_asset(self, asset_id: str, detail: str = "") -> VisualAssetRecord:
        with self.database.transaction() as connection:
            asset = connection.execute(
                "SELECT * FROM visual_assets WHERE id = ?", (asset_id,)
            ).fetchone()
            if asset is None:
                raise GameStateError(f"Unknown visual asset: {asset_id}")
            connection.execute(
                "UPDATE visual_assets SET status = 'rejected', canonical = 0, active = 0 WHERE id = ?",
                (asset_id,),
            )
            self._append_history(
                connection, asset_id, str(asset["campaign_id"]), "rejected",
                str(asset["state_signature"]), detail.strip() or "Visual rejected.",
            )
            result = connection.execute(
                "SELECT * FROM visual_assets WHERE id = ?", (asset_id,)
            ).fetchone()
        return _record_from_row(result, self.assets_root)

    def resolve(
        self,
        *,
        campaign_id: str,
        asset_kind: str,
        subject_type: str,
        subject_id: str,
        signature: str | None = None,
    ) -> VisualAssetRecord | None:
        signature = signature or self.current_state_signature(
            campaign_id, subject_type, subject_id
        )
        with self.database.transaction() as connection:
            record = resolve_visual_record(
                connection,
                self.assets_root,
                campaign_id=campaign_id,
                asset_kind=asset_kind,
                subject_type=subject_type,
                subject_id=subject_id,
                signature=signature,
            )
            if record is not None and record.status == "confirmed":
                exact = record.state_signature == signature
                connection.execute(
                    """
                    UPDATE visual_assets SET use_count = use_count + 1,
                        last_used_at = CURRENT_TIMESTAMP WHERE id = ?
                    """,
                    (record.id,),
                )
                self._append_history(
                    connection, record.id, campaign_id, "reused", signature,
                    "Exact state match reused." if exact else "Canonical fallback reused.",
                )
                row = connection.execute(
                    "SELECT * FROM visual_assets WHERE id = ?", (record.id,)
                ).fetchone()
                return _record_from_row(row, self.assets_root)
            if record is not None and record.status == "missing":
                connection.execute(
                    "UPDATE visual_assets SET canonical = 0, active = 0 WHERE id = ?",
                    (record.id,),
                )
                self._append_history(
                    connection, record.id, campaign_id, "missing", signature,
                    "Registered asset file was unavailable during resolution.",
                )
                row = connection.execute(
                    "SELECT * FROM visual_assets WHERE id = ?", (record.id,)
                ).fetchone()
                return _record_from_row(row, self.assets_root)
            return record

    def history(self, asset_id: str) -> tuple[VisualHistoryRecord, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM visual_asset_history WHERE asset_id = ? "
                "ORDER BY created_at, id",
                (asset_id,),
            ).fetchall()
        return tuple(
            VisualHistoryRecord(
                id=str(row["id"]),
                asset_id=str(row["asset_id"]),
                action=str(row["action"]),
                state_signature=str(row["state_signature"]),
                detail=str(row["detail"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        )

    @staticmethod
    def _append_history(
        connection: sqlite3.Connection,
        asset_id: str,
        campaign_id: str,
        action: str,
        signature: str,
        detail: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO visual_asset_history(
                id, asset_id, campaign_id, action, state_signature, detail
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"visual-history-{uuid4().hex}", asset_id, campaign_id, action, signature, detail),
        )
