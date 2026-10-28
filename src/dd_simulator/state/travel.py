"""Deterministic world travel, route hazards, discovery, and camping."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Protocol
from uuid import uuid4

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.errors import GameStateError
from dd_simulator.state.quests import check_deadlines, progress_quests


class TravelNarrationProvider(Protocol):
    """Optional prose-only boundary; callers cannot supply mechanical values."""

    def narrate_travel(self, context: dict[str, object]) -> str: ...

    def narrate_camp(self, context: dict[str, object]) -> str: ...


@dataclass(frozen=True, slots=True)
class TravelResult:
    history_id: str
    route_id: str
    origin_id: str
    destination_id: str
    destination_name: str
    summary: str
    quest_updates: tuple[str, ...]
    encounter_required: bool


@dataclass(frozen=True, slots=True)
class CampResult:
    history_id: str
    location_id: str
    summary: str
    deadline_updates: tuple[str, ...]


class TravelService:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database

    def travel(
        self,
        campaign_id: str,
        route_id: str,
        *,
        narrator: TravelNarrationProvider | None = None,
    ) -> TravelResult:
        generated_prose = ""
        if narrator is not None:
            with self.database.connect() as read_connection:
                read_active_combat = read_connection.execute(
                    "SELECT 1 FROM combat_encounters WHERE campaign_id = ? AND status = 'active'",
                    (campaign_id,),
                ).fetchone()
                read_current = self._current_location(read_connection, campaign_id)
                read_route = read_connection.execute(
                    "SELECT * FROM travel_routes WHERE id = ? AND campaign_id = ?",
                    (route_id, campaign_id),
                ).fetchone()
                if (
                    read_active_combat is None
                    and read_route is not None
                    and bool(read_route["discovered"])
                    and str(read_route["status"]) == "open"
                    and (
                        str(read_route["origin_location_id"]) == str(read_current["id"])
                        or bool(read_route["bidirectional"])
                        and str(read_route["destination_location_id"]) == str(read_current["id"])
                    )
                ):
                    read_destination_id = (
                        str(read_route["destination_location_id"])
                        if str(read_route["origin_location_id"]) == str(read_current["id"])
                        else str(read_route["origin_location_id"])
                    )
                    read_destination = read_connection.execute(
                        "SELECT * FROM locations WHERE id = ? AND campaign_id = ?",
                        (read_destination_id, campaign_id),
                    ).fetchone()
                    if read_destination is not None and bool(read_destination["discovered"]):
                        generated_prose = self._travel_prose(
                            narrator, read_current, read_destination, read_route, ""
                        )
        with self.database.transaction() as connection:
            self._require_no_combat(connection, campaign_id)
            current = self._current_location(connection, campaign_id)
            route = connection.execute(
                "SELECT * FROM travel_routes WHERE id = ? AND campaign_id = ?",
                (route_id, campaign_id),
            ).fetchone()
            if route is None or not bool(route["discovered"]):
                raise GameStateError("That travel route is not known.")
            status = str(route["status"])
            if status != "open":
                reason = str(route["requirement"] or "The route is not currently open.")
                raise GameStateError(f"Travel is {status}: {reason}")
            origin_id = str(current["id"])
            if str(route["origin_location_id"]) == origin_id:
                destination_id = str(route["destination_location_id"])
            elif bool(route["bidirectional"]) and str(route["destination_location_id"]) == origin_id:
                destination_id = str(route["origin_location_id"])
            else:
                raise GameStateError("That route does not begin at the current location.")
            destination = connection.execute(
                "SELECT * FROM locations WHERE id = ? AND campaign_id = ?",
                (destination_id, campaign_id),
            ).fetchone()
            if destination is None or not bool(destination["discovered"]):
                raise GameStateError("The destination has not been discovered.")

            character = connection.execute(
                "SELECT id FROM characters WHERE campaign_id = ? AND is_player = 1",
                (campaign_id,),
            ).fetchone()
            if character is None:
                raise GameStateError("Travel requires an active player character.")
            stamina_cost = int(route["stamina_cost"])
            stamina = connection.execute(
                "SELECT * FROM character_resources WHERE character_id = ? "
                "AND resource_type = 'stamina'",
                (character["id"],),
            ).fetchone()
            if stamina_cost and (stamina is None or int(stamina["current_value"]) < stamina_cost):
                raise GameStateError(
                    f"Travel requires {stamina_cost} stamina, but the player does not have enough."
                )

            clock = connection.execute(
                "SELECT * FROM campaign_clock WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
            if clock is None:
                raise GameStateError("The campaign clock is unavailable.")
            departed_day = int(clock["day"])
            departed_minute = int(clock["minute_of_day"])
            arrived_day, arrived_minute, period, time_label = self._advance_values(
                departed_day, departed_minute, int(route["travel_minutes"])
            )
            if stamina is not None and stamina_cost:
                connection.execute(
                    "UPDATE character_resources SET current_value = current_value - ? WHERE id = ?",
                    (stamina_cost, stamina["id"]),
                )
            connection.execute(
                "UPDATE campaign_clock SET day = ?, minute_of_day = ?, period = ?, "
                "time_label = ?, turn_number = turn_number + 1 WHERE campaign_id = ?",
                (arrived_day, arrived_minute, period, time_label, campaign_id),
            )
            connection.execute(
                "UPDATE locations SET is_current = 0 WHERE campaign_id = ?", (campaign_id,)
            )
            connection.execute(
                "UPDATE locations SET is_current = 1, discovered = 1, "
                "first_discovered_at = COALESCE(first_discovered_at, CURRENT_TIMESTAMP), "
                "last_visited_at = CURRENT_TIMESTAMP, visit_count = visit_count + 1 WHERE id = ?",
                (destination_id,),
            )

            fallback = (
                f"The party travels {route['distance_miles']} miles from {current['name']} "
                f"to {destination['name']} and arrives {time_label}."
            )
            prose = generated_prose or fallback
            deadline_updates = check_deadlines(connection, campaign_id)
            quest_updates = progress_quests(
                connection,
                campaign_id,
                "travel",
                destination_id,
                detail=f"Arrived at {destination['name']}. {prose}",
            )
            updates = (*deadline_updates, *quest_updates)
            encounter_required = self._encounter_required(
                route_id,
                int(route["danger_rating"]),
                arrived_day,
                arrived_minute,
                int(destination["visit_count"]) + 1,
            )
            summary = prose + (" Danger interrupts the arrival." if encounter_required else "")
            history_id = f"travel-{uuid4().hex}"
            connection.execute(
                "INSERT INTO travel_history(id, campaign_id, route_id, origin_location_id, "
                "destination_location_id, departed_day, departed_minute, arrived_day, "
                "arrived_minute, stamina_spent, outcome, summary) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    history_id, campaign_id, route_id, origin_id, destination_id,
                    departed_day, departed_minute, arrived_day, arrived_minute,
                    stamina_cost, "encounter" if encounter_required else "arrived", summary,
                ),
            )
            self._append_messages(
                connection,
                campaign_id,
                (("player", f"Travel to {destination['name']}"), ("narrative", prose)),
            )
            self._append_event(connection, campaign_id, "travel", summary)
            return TravelResult(
                history_id,
                route_id,
                origin_id,
                destination_id,
                str(destination["name"]),
                summary,
                tuple(updates),
                encounter_required,
            )

    def camp(
        self,
        campaign_id: str,
        *,
        duration_minutes: int = 480,
        narrator: TravelNarrationProvider | None = None,
    ) -> CampResult:
        if duration_minutes not in {240, 480}:
            raise GameStateError("Camp duration must be four or eight hours.")
        generated_prose = ""
        if narrator is not None:
            with self.database.connect() as read_connection:
                read_location = self._current_location(read_connection, campaign_id)
                read_active_combat = read_connection.execute(
                    "SELECT 1 FROM combat_encounters WHERE campaign_id = ? AND status = 'active'",
                    (campaign_id,),
                ).fetchone()
                if read_active_combat is None and bool(read_location["can_camp"]):
                    generated_prose = self._camp_prose(
                        narrator, read_location, duration_minutes, ""
                    )
        with self.database.transaction() as connection:
            self._require_no_combat(connection, campaign_id)
            location = self._current_location(connection, campaign_id)
            if not bool(location["can_camp"]):
                raise GameStateError("Camping is not permitted at this location.")
            clock = connection.execute(
                "SELECT * FROM campaign_clock WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
            character = connection.execute(
                "SELECT id FROM characters WHERE campaign_id = ? AND is_player = 1",
                (campaign_id,),
            ).fetchone()
            if clock is None or character is None:
                raise GameStateError("Camping requires a complete campaign state.")
            started_day = int(clock["day"])
            started_minute = int(clock["minute_of_day"])
            day, minute, period, time_label = self._advance_values(
                started_day, started_minute, duration_minutes
            )
            recovery_divisor = 2 if duration_minutes == 480 else 4
            connection.execute(
                "UPDATE character_resources SET current_value = CASE "
                "WHEN resource_type = 'experience' THEN current_value "
                "WHEN resource_type = 'spell_slots' AND ? = 480 THEN maximum_value "
                "ELSE MIN(maximum_value, current_value + MAX(1, maximum_value / ?)) END "
                "WHERE character_id = ?",
                (duration_minutes, recovery_divisor, character["id"]),
            )
            if duration_minutes == 480:
                connection.execute(
                    "UPDATE abilities SET cooldown_remaining = 0, current_uses = maximum_uses "
                    "WHERE character_id = ?",
                    (character["id"],),
                )
            connection.execute(
                "UPDATE campaign_clock SET day = ?, minute_of_day = ?, period = ?, "
                "time_label = ?, turn_number = turn_number + 1 WHERE campaign_id = ?",
                (day, minute, period, time_label, campaign_id),
            )
            fallback = (
                f"The party makes camp at {location['name']} for "
                f"{duration_minutes // 60} hours and breaks camp {time_label}."
            )
            prose = generated_prose or fallback
            updates = check_deadlines(connection, campaign_id)
            history_id = f"camp-{uuid4().hex}"
            connection.execute(
                "INSERT INTO camp_history(id, campaign_id, location_id, started_day, "
                "started_minute, duration_minutes, summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    history_id, campaign_id, location["id"], started_day,
                    started_minute, duration_minutes, prose,
                ),
            )
            self._append_messages(
                connection,
                campaign_id,
                (("player", "Make camp"), ("narrative", prose)),
            )
            self._append_event(connection, campaign_id, "rest", prose)
            return CampResult(history_id, str(location["id"]), prose, updates)

    @staticmethod
    def attach_encounter(
        connection: sqlite3.Connection, campaign_id: str, history_id: str, encounter_id: str
    ) -> None:
        connection.execute(
            "UPDATE travel_history SET encounter_id = ?, outcome = 'encounter' "
            "WHERE id = ? AND campaign_id = ?",
            (encounter_id, history_id, campaign_id),
        )

    @staticmethod
    def _require_no_combat(connection: sqlite3.Connection, campaign_id: str) -> None:
        active = connection.execute(
            "SELECT 1 FROM combat_encounters WHERE campaign_id = ? AND status = 'active'",
            (campaign_id,),
        ).fetchone()
        if active is not None:
            raise GameStateError("Travel and camping are unavailable during combat.")

    @staticmethod
    def _current_location(connection: sqlite3.Connection, campaign_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM locations WHERE campaign_id = ? AND is_current = 1",
            (campaign_id,),
        ).fetchone()
        if row is None:
            raise GameStateError("The campaign has no current location.")
        return row

    @staticmethod
    def _advance_values(day: int, minute: int, amount: int) -> tuple[int, int, str, str]:
        total = minute + amount
        new_day = day + total // 1440
        new_minute = total % 1440
        hour = new_minute // 60
        period = (
            "Morning" if 5 <= hour < 12 else
            "Afternoon" if 12 <= hour < 17 else
            "Evening" if 17 <= hour < 21 else "Night"
        )
        return new_day, new_minute, period, f"{period}, Day {new_day}"

    @staticmethod
    def _encounter_required(
        route_id: str, danger: int, day: int, minute: int, visit_count: int
    ) -> bool:
        if danger <= 0:
            return False
        deterministic_roll = (
            sum(ord(character) for character in route_id)
            + day * 31
            + minute
            + visit_count * 7
        ) % 10 + 1
        return deterministic_roll <= danger

    @staticmethod
    def _travel_prose(
        narrator: TravelNarrationProvider | None,
        origin: sqlite3.Row,
        destination: sqlite3.Row,
        route: sqlite3.Row,
        fallback: str,
    ) -> str:
        if narrator is None:
            return fallback
        try:
            value = narrator.narrate_travel(
                {
                    "origin": str(origin["name"]),
                    "destination": str(destination["name"]),
                    "biome": str(destination["biome"]),
                    "distance_miles": int(route["distance_miles"]),
                    "route_description": str(route["description"]),
                }
            ).strip()
        except Exception:
            return fallback
        return value[:1200] if value else fallback

    @staticmethod
    def _camp_prose(
        narrator: TravelNarrationProvider | None,
        location: sqlite3.Row,
        duration_minutes: int,
        fallback: str,
    ) -> str:
        if narrator is None:
            return fallback
        try:
            value = narrator.narrate_camp(
                {
                    "location": str(location["name"]),
                    "biome": str(location["biome"]),
                    "duration_hours": duration_minutes // 60,
                }
            ).strip()
        except Exception:
            return fallback
        return value[:1200] if value else fallback

    @staticmethod
    def _append_messages(
        connection: sqlite3.Connection,
        campaign_id: str,
        messages: tuple[tuple[str, str], ...],
    ) -> None:
        turn = int(
            connection.execute(
                "SELECT turn_number FROM campaign_clock WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]
        )
        for sequence, (kind, value) in enumerate(messages):
            connection.execute(
                "INSERT INTO narrative_messages(id, campaign_id, turn_number, sequence, kind, text) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"message-{uuid4().hex}", campaign_id, turn, sequence, kind, value),
            )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection, campaign_id: str, category: str, summary: str
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]
        )
        time_label = str(
            connection.execute(
                "SELECT time_label FROM campaign_clock WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]
        )
        connection.execute(
            "INSERT INTO events(id, campaign_id, time_label, category, summary, sequence, is_recent) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (f"event-{uuid4().hex}", campaign_id, time_label, category, summary[:700], sequence),
        )
        connection.execute(
            "UPDATE events SET is_recent = 0 WHERE campaign_id = ? AND sequence <= ?",
            (campaign_id, sequence - 5),
        )
