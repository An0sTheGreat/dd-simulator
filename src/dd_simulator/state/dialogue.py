"""Deterministic NPC conversations with optional prose-only narration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import sqlite3
from typing import Any, Iterator, Protocol
from uuid import uuid4

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.errors import GameStateError
from dd_simulator.state.quests import progress_quests
from dd_simulator.state.presets import active_preset_context
from dd_simulator.state.turns import SkillCheckResult, claim_turn_notes, record_turn_note


LOGGER = logging.getLogger(__name__)


SUGGESTED_RESPONSES = (
    "Ask what has happened here recently.",
    "Ask whether they need any help.",
    "Ask what they know about this area.",
    "Try to persuade them to share more.",
    "Study their reaction for hidden motives.",
    "End the conversation politely.",
)


class DialogueNarrationProvider(Protocol):
    def phrase_dialogue(self, *, context: dict[str, object]) -> object: ...


@dataclass(frozen=True, slots=True)
class DialogueNarration:
    speech: str
    monologue: str
    quest_offer: dict[str, Any] | None = None

    def __iter__(self) -> Iterator[str]:
        yield self.speech
        yield self.monologue


@dataclass(frozen=True, slots=True)
class DialogueResult:
    npc_id: str
    player_text: str
    npc_text: str
    monologue: str
    check_summary: str
    relationship_delta: int
    quest_updates: tuple[str, ...]
    skill_check: SkillCheckResult | None = None


class DialogueService:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database

    def resolve(
        self,
        campaign_id: str,
        npc_id: str,
        player_text: str,
        *,
        narrator: DialogueNarrationProvider | None = None,
    ) -> DialogueResult:
        text = " ".join(player_text.split())
        if not text:
            raise GameStateError("Enter a response before sending.")
        if len(text) > 2000:
            raise GameStateError("Dialogue responses are limited to 2,000 characters.")

        with self.database.connect() as connection:
            context = self._build_context(connection, campaign_id, npc_id, text)
        fallback = self._fallback_reply(context)
        npc_text, monologue = fallback
        quest_offer: dict[str, Any] | None = None
        if narrator is not None:
            try:
                phrased = narrator.phrase_dialogue(context=context)
                if isinstance(phrased, DialogueNarration):
                    npc_text = phrased.speech.strip()[:2000]
                    monologue = phrased.monologue.strip()[:1000]
                    quest_offer = phrased.quest_offer
                elif (
                    isinstance(phrased, tuple) and len(phrased) == 2
                    and all(isinstance(value, str) for value in phrased)
                    and phrased[0].strip()
                ):
                    npc_text, monologue = phrased[0].strip()[:2000], phrased[1].strip()[:1000]
                    quest_offer = None
                else:
                    quest_offer = None
            except Exception as exc:
                LOGGER.warning("NPC dialogue generation failed before commit: %s", exc)
                raise GameStateError(
                    "The local model could not generate this NPC response. Your input was not "
                    f"committed; check the loaded model and retry. Details: {exc}"
                ) from exc

        with self.database.transaction() as connection:
            fresh = self._build_context(connection, campaign_id, npc_id, text)
            if fresh["turn_number"] != context["turn_number"]:
                raise GameStateError("The conversation changed while the response was generated.")
            return self._commit(connection, fresh, npc_text, monologue, quest_offer)

    @staticmethod
    def _build_context(
        connection: sqlite3.Connection,
        campaign_id: str,
        npc_id: str,
        text: str,
    ) -> dict[str, object]:
        npc = connection.execute(
            "SELECT npcs.*, locations.name AS location_name FROM npcs "
            "LEFT JOIN locations ON locations.id = npcs.location_id "
            "WHERE npcs.id = ? AND npcs.campaign_id = ?",
            (npc_id, campaign_id),
        ).fetchone()
        current = connection.execute(
            "SELECT id, name FROM locations WHERE campaign_id = ? AND is_current = 1",
            (campaign_id,),
        ).fetchone()
        character = connection.execute(
            "SELECT id, name, level, character_class, species, background, "
            "personality_json, primary_strength, meaningful_flaw, motivation "
            "FROM characters WHERE campaign_id = ? AND is_player = 1",
            (campaign_id,),
        ).fetchone()
        preferences = connection.execute(
            "SELECT tone, difficulty, content_preferences FROM campaign_preferences "
            "WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        location = connection.execute(
            "SELECT id, name, region, weather, danger, description FROM locations "
            "WHERE campaign_id = ? AND is_current = 1",
            (campaign_id,),
        ).fetchone()
        if location is not None:
            current = location
        if npc is None or current is None or character is None:
            raise GameStateError("That conversation is unavailable.")
        if str(npc["location_id"] or "") != str(current["id"]):
            raise GameStateError(f"{npc['name']} is not at your current location.")
        if not bool(npc["available"]) or str(npc["status"]) in {"unavailable", "departed", "deceased"}:
            raise GameStateError(f"{npc['name']} is currently {npc['status']}.")
        turn_number = int(connection.execute(
            "SELECT COUNT(*) + 1 FROM npc_conversations WHERE campaign_id = ? AND npc_id = ?",
            (campaign_id, npc_id),
        ).fetchone()[0])
        relationship = connection.execute(
            "SELECT score FROM relationships WHERE campaign_id = ? "
            "AND source_entity_id = ? AND target_entity_id = ?",
            (campaign_id, character["id"], npc_id),
        ).fetchone()
        memories = connection.execute(
            "SELECT summary FROM npc_memories WHERE campaign_id = ? AND npc_id = ? "
            "ORDER BY importance DESC, created_at DESC LIMIT 6", (campaign_id, npc_id),
        ).fetchall()
        recent_rows = connection.execute(
            "SELECT turn_number, player_text, npc_text, monologue FROM npc_conversations "
            "WHERE campaign_id = ? AND npc_id = ? ORDER BY turn_number DESC LIMIT 8",
            (campaign_id, npc_id),
        ).fetchall()
        recent_conversation = [dict(row) for row in reversed(recent_rows)]
        quest_rows = connection.execute(
            "SELECT quests.id, quests.title, quests.summary, quest_objectives.text, "
            "quest_objectives.completed FROM quests LEFT JOIN quest_objectives "
            "ON quest_objectives.quest_id = quests.id "
            "WHERE quests.campaign_id = ? AND quests.status = 'active' "
            "ORDER BY quests.display_order, quest_objectives.display_order LIMIT 12",
            (campaign_id,),
        ).fetchall()
        check_type = DialogueService._check_type(text)
        modifier = 0
        if check_type:
            attribute = "Strength" if check_type == "intimidation" else "Wisdom" if check_type == "insight" else "Charisma"
            row = connection.execute(
                "SELECT modifier FROM character_attributes WHERE character_id = ? AND lower(name) = lower(?)",
                (character["id"], attribute),
            ).fetchone()
            modifier = 0 if row is None else int(row["modifier"])
            skill = connection.execute(
                "SELECT bonus, level FROM skills WHERE character_id = ? AND lower(name) = lower(?)",
                (character["id"], check_type),
            ).fetchone()
            if skill is not None:
                modifier += int(skill["bonus"]) + int(skill["level"]) // 20
        seed = hashlib.sha256(f"{campaign_id}:{npc_id}:{turn_number}:{text.casefold()}".encode()).digest()
        roll = seed[0] % 20 + 1 if check_type else None
        campaign_difficulty = (
            "adventurer" if preferences is None else str(preferences["difficulty"]).casefold()
        )
        difficulty = (
            12
            + (2 if str(npc["status"]) in {"suspicious", "hostile"} else 0)
            + {"story": -2, "adventurer": 0, "veteran": 2, "deadly": 4}.get(
                campaign_difficulty, 0
            )
            if check_type else None
        )
        total = None if roll is None else roll + modifier
        success = total is not None and total >= int(difficulty)
        context = {
            "campaign_id": campaign_id, "npc": dict(npc), "character": dict(character),
            "location": dict(current), "player_text": text, "turn_number": turn_number,
            "relationship_score": 0 if relationship is None else int(relationship["score"]),
            "memories": [str(row["summary"]) for row in memories],
            "recent_conversation": recent_conversation,
            "active_quests": [dict(row) for row in quest_rows],
            "campaign_preferences": {} if preferences is None else dict(preferences),
            "check_type": check_type, "roll": roll, "modifier": modifier,
            "difficulty": difficulty, "total": total, "success": success,
        }
        preset_context = active_preset_context(connection, campaign_id)
        if preset_context is not None:
            context["preset_campaign"] = preset_context
        return context

    @staticmethod
    def _check_type(text: str) -> str:
        lowered = text.casefold()
        if any(word in lowered for word in ("intimidate", "threaten", "or else", "fear")):
            return "intimidation"
        if any(word in lowered for word in ("deceive", "lie", "pretend", "bluff")):
            return "deception"
        if any(word in lowered for word in ("persuade", "convince", "please", "share more")):
            return "persuasion"
        if any(word in lowered for word in ("hidden motive", "study their reaction", "insight", "trust you")):
            return "insight"
        return ""

    @staticmethod
    def _fallback_reply(context: dict[str, object]) -> tuple[str, str]:
        npc = context["npc"]
        assert isinstance(npc, dict)
        name = str(npc["name"])
        check_type = str(context["check_type"])
        if check_type and bool(context["success"]):
            speech = f'"You make a fair point," {name} says. "I will tell you what I know."'
            monologue = "Their guarded posture eases; the appeal clearly landed."
        elif check_type:
            speech = f'{name} shakes their head. "That approach will not sway me."'
            monologue = "Their expression closes, the failed attempt sharpening their caution."
        elif "help" in str(context["player_text"]).casefold():
            speech = f'{name} considers the offer. "There may be something you can do."'
            monologue = "They weigh your reliability before continuing."
        elif "area" in str(context["player_text"]).casefold() or "happened" in str(context["player_text"]).casefold():
            speech = f'{name} glances toward the road. "Keep your eyes open. This place remembers every traveler."'
            monologue = "The warning is sincere, though deliberately incomplete."
        else:
            speech = f'{name} listens carefully. "Go on. I am listening."'
            monologue = "Their attention remains fixed on your next words."
        return speech, monologue

    @staticmethod
    def _commit(
        connection: sqlite3.Connection,
        context: dict[str, object],
        npc_text: str,
        monologue: str,
        quest_offer: dict[str, Any] | None = None,
    ) -> DialogueResult:
        npc = context["npc"]
        character = context["character"]
        assert isinstance(npc, dict) and isinstance(character, dict)
        check_type = str(context["check_type"])
        success = bool(context["success"])
        delta = 2 if success else -3 if check_type else 1
        conversation_id = f"npc-conversation-{uuid4().hex}"
        outcome = "success" if success else "failure" if check_type else "neutral"
        connection.execute(
            "INSERT INTO npc_conversations(id, campaign_id, npc_id, turn_number, player_text, "
            "npc_text, monologue, check_type, d20_roll, modifier, total, difficulty, outcome, relationship_delta) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, context["campaign_id"], npc["id"], context["turn_number"],
             context["player_text"], npc_text, monologue, check_type, context["roll"],
             context["modifier"], context["total"], context["difficulty"], outcome, delta),
        )
        relationship_update = connection.execute(
            "UPDATE relationships SET score = MAX(-100, MIN(100, score + ?)) "
            "WHERE campaign_id = ? AND source_entity_id = ? AND target_entity_id = ?",
            (delta, context["campaign_id"], character["id"], npc["id"]),
        )
        if relationship_update.rowcount:
            record_turn_note(
                connection, context["campaign_id"], "relationship", f"{npc['name']} {delta:+d}"
            )
        score = int(context["relationship_score"]) + delta
        status = "friendly" if score >= 25 else "suspicious" if score <= -20 else "neutral"
        connection.execute("UPDATE npcs SET status = ?, disposition = ? WHERE id = ?", (status, status, npc["id"]))
        if check_type or any(word in str(context["player_text"]).casefold() for word in ("help", "secret", "promise", "quest")):
            connection.execute(
                "INSERT INTO npc_memories(id, campaign_id, npc_id, summary, importance, source_conversation_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"npc-memory-{uuid4().hex}", context["campaign_id"], npc["id"],
                 f"{character['name']} said: {context['player_text']}"[:500], 3 if check_type else 2, conversation_id),
            )
        quest_updates = list(progress_quests(
            connection, str(context["campaign_id"]), "dialogue", str(npc["name"]),
            detail=str(context["player_text"]),
        ))
        task_language = npc_text.casefold()
        if quest_offer is not None and not any(
            marker in task_language for marker in (
                "need you", "could you", "will you", "help me", "task", "work for",
                "bring", "find", "recover", "deliver", "investigate", "defeat",
            )
        ):
            quest_offer = None
        discovered = DialogueService._commit_quest_offer(connection, context, quest_offer)
        if discovered:
            quest_updates.append(discovered)
        if npc.get("offers_quest_id"):
            connection.execute(
                "UPDATE quests SET status = 'active', started_day = COALESCE(started_day, 1) "
                "WHERE id = ? AND status = 'rumored'", (npc["offers_quest_id"],),
            )
        if success and npc.get("reveals_location_id"):
            connection.execute(
                "UPDATE locations SET discovered = 1, first_discovered_at = COALESCE(first_discovered_at, CURRENT_TIMESTAMP) "
                "WHERE id = ?", (npc["reveals_location_id"],),
            )
        if success and npc.get("reveals_route_id"):
            connection.execute(
                "UPDATE travel_routes SET discovered = 1, status = CASE WHEN status = 'hidden' THEN 'open' ELSE status END "
                "WHERE id = ?", (npc["reveals_route_id"],),
            )
        connection.execute(
            "INSERT INTO faction_reputation(campaign_id, faction, score) VALUES (?, ?, ?) "
            "ON CONFLICT(campaign_id, faction) DO UPDATE SET score = score + excluded.score",
            (context["campaign_id"], npc["faction"], 1 if success else 0),
        )
        campaign_turn = connection.execute(
            "SELECT turn_number FROM campaign_clock WHERE campaign_id = ?",
            (context["campaign_id"],),
        ).fetchone()
        turn_number = 0 if campaign_turn is None else int(campaign_turn["turn_number"])
        next_sequence = int(connection.execute(
            "SELECT COALESCE(MAX(sequence), -1) + 1 FROM narrative_messages "
            "WHERE campaign_id = ? AND turn_number = ?",
            (context["campaign_id"], turn_number),
        ).fetchone()[0])
        transcript = [
            (
                f"{conversation_id}-player", context["campaign_id"], turn_number,
                next_sequence, "player", context["player_text"], None,
            )
        ]
        if monologue.strip():
            transcript.append(
                (
                    f"{conversation_id}-monologue", context["campaign_id"], turn_number,
                    next_sequence + len(transcript), "monologue", monologue, None,
                )
            )
        transcript.append(
            (
                f"{conversation_id}-spoken", context["campaign_id"], turn_number,
                next_sequence + len(transcript), "spoken", npc_text, npc["id"],
            )
        )
        connection.executemany(
            "INSERT INTO narrative_messages("
            "id, campaign_id, turn_number, sequence, kind, text, speaker_npc_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            transcript,
        )
        claim_turn_notes(connection, context["campaign_id"], turn_number)
        sequence = int(connection.execute(
            "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE campaign_id = ?",
            (context["campaign_id"],),
        ).fetchone()[0])
        clock = connection.execute(
            "SELECT time_label FROM campaign_clock WHERE campaign_id = ?", (context["campaign_id"],),
        ).fetchone()
        connection.execute(
            "INSERT INTO events(id, campaign_id, time_label, category, summary, sequence, is_recent) "
            "VALUES (?, ?, ?, 'npc', ?, ?, 1)",
            (f"event-{uuid4().hex}", context["campaign_id"], clock["time_label"],
             f"Spoke with {npc['name']}. {npc_text}"[:700], sequence),
        )
        connection.execute(
            "DELETE FROM npc_conversations WHERE id IN (SELECT id FROM npc_conversations "
            "WHERE campaign_id = ? AND npc_id = ? ORDER BY turn_number DESC LIMIT -1 OFFSET 20)",
            (context["campaign_id"], npc["id"]),
        )
        check_summary = ""
        skill_check = None
        if check_type:
            check_summary = (
                f"{check_type.title()} check: d20 {context['roll']} + {context['modifier']} "
                f"= {context['total']} vs DC {context['difficulty']} — {outcome}."
            )
            skill_check = SkillCheckResult(
                name=check_type.title(), roll=int(context["roll"]),
                modifier=int(context["modifier"]), total=int(context["total"]),
                target=int(context["difficulty"]), success=success,
            )
        return DialogueResult(
            npc_id=str(npc["id"]), player_text=str(context["player_text"]), npc_text=npc_text,
            monologue=monologue, check_summary=check_summary, relationship_delta=delta,
            quest_updates=tuple(quest_updates),
            skill_check=skill_check,
        )

    @staticmethod
    def _commit_quest_offer(
        connection: sqlite3.Connection,
        context: dict[str, object],
        offer: dict[str, Any] | None,
    ) -> str:
        """Validate and persist one grounded NPC task inside the dialogue transaction."""

        if not isinstance(offer, dict):
            return ""
        npc = context["npc"]
        assert isinstance(npc, dict)
        existing_id = str(npc.get("offers_quest_id") or "")
        if existing_id:
            existing = connection.execute(
                "SELECT title, status FROM quests WHERE id = ?", (existing_id,),
            ).fetchone()
            if existing is not None and str(existing["status"]) in {"rumored", "active"}:
                return ""
        title = " ".join(str(offer.get("title") or "").split())[:100]
        summary = " ".join(str(offer.get("summary") or "").split())[:1000]
        raw_objectives = offer.get("objectives")
        if not title or not summary or not isinstance(raw_objectives, list):
            return ""
        objectives: list[tuple[str, bool, str, str]] = []
        allowed_triggers = {
            "combat", "travel", "item_collect", "item_use", "item_examine",
            "dialogue", "custom_action",
        }
        for raw in raw_objectives[:5]:
            if not isinstance(raw, dict):
                return ""
            text = " ".join(str(raw.get("text") or "").split())[:300]
            if not text:
                return ""
            trigger_type = str(raw.get("trigger_type") or "custom_action").casefold()
            if trigger_type not in allowed_triggers:
                trigger_type = "custom_action"
            trigger_target = " ".join(str(raw.get("trigger_target") or "").split())[:200]
            objectives.append((text, bool(raw.get("optional", False)), trigger_type, trigger_target))
        if not 2 <= len(objectives) <= 5:
            return ""
        duplicate = connection.execute(
            "SELECT id FROM quests WHERE campaign_id = ? AND lower(title) = lower(?) "
            "AND status IN ('rumored', 'active')",
            (context["campaign_id"], title),
        ).fetchone()
        if duplicate is not None:
            return ""
        preference = context.get("campaign_preferences")
        difficulty = str(preference.get("difficulty", "Adventurer")) if isinstance(preference, dict) else "Adventurer"
        multiplier = {"story": 0.75, "adventurer": 1.0, "veteran": 1.35, "deadly": 1.75}.get(difficulty.casefold(), 1.0)
        quest_id = f"quest-{uuid4().hex}"
        display_order = int(connection.execute(
            "SELECT COALESCE(MAX(display_order), -1) + 1 FROM quests WHERE campaign_id = ?",
            (context["campaign_id"],),
        ).fetchone()[0])
        connection.execute(
            "INSERT INTO quests(id, campaign_id, title, status, summary, progress_maximum, "
            "display_order, quest_type, started_day, started_minute, reward_experience, "
            "reward_currency, reward_reputation, reward_faction, reward_items_json) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?, 'optional', 1, 480, ?, ?, 1, ?, '[]')",
            (quest_id, context["campaign_id"], title, summary, len(objectives), display_order,
             int(round((50 + 25 * len(objectives)) * multiplier)),
             int(round((10 + 8 * len(objectives)) * multiplier)), str(npc.get("faction") or "")),
        )
        required_indices = tuple(
            index for index, (_text, optional, _trigger_type, _trigger_target)
            in enumerate(objectives) if not optional
        )
        final_required_index = required_indices[-1] if required_indices else -1
        for index, (text, optional, trigger_type, trigger_target) in enumerate(objectives):
            connection.execute(
                "INSERT INTO quest_objectives(id, quest_id, text, optional, display_order, "
                "trigger_type, trigger_target, completion_gate) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"objective-{uuid4().hex}", quest_id, text, int(optional), index,
                 trigger_type, trigger_target, int(index == final_required_index)),
            )
        connection.execute("UPDATE npcs SET offers_quest_id = ? WHERE id = ?", (quest_id, npc["id"]))
        connection.execute(
            "INSERT INTO quest_updates(id, quest_id, update_type, summary) "
            "VALUES (?, ?, 'activated', ?)",
            (f"quest-update-{uuid4().hex}", quest_id, f"Quest discovered: {title}"),
        )
        return f"Quest discovered: {title}."
