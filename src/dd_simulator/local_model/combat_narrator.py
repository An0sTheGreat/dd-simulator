"""Constrained local model narration and enemy intent for resolved combat turns."""

from __future__ import annotations

import json
from typing import Any

from dd_simulator.local_model.client import LocalModelClient
from dd_simulator.local_model.errors import LocalModelError, LocalModelResponseError
from dd_simulator.local_model.prompts import DUNGEON_MASTER_SYSTEM
from dd_simulator.state.combat import CombatNarrationOutcome
from dd_simulator.state.turns import (
    NarrativeSegment,
    limit_narrative_segments,
    sanitize_model_text,
)


class LocalModelCombatNarrator:
    """Request prose and bounded intent choices without accepting mechanics."""

    def __init__(self, client: LocalModelClient) -> None:
        self.client = client

    def resolve_combat_turn(
        self,
        *,
        context: dict[str, Any],
        allowed_intents: dict[str, tuple[str, ...]],
    ) -> CombatNarrationOutcome:
        model = self.client.preferred_model_id()
        last_error: LocalModelError | None = None
        checker = getattr(self.client, "uses_plain_json", None)
        compatibility = bool(checker(model)) if callable(checker) else False
        for attempt in range(2):
            try:
                response = self.client._json_request(  # noqa: SLF001
                    "/chat/completions",
                    method="POST",
                    payload=self._payload(
                        model=model,
                        context=context,
                        allowed_intents=allowed_intents,
                        compatibility=compatibility,
                    ),
                )
                return self._parse(response, allowed_intents)
            except LocalModelError as exc:
                last_error = exc
                if attempt or not LocalModelClient.supports_schema_fallback(exc):
                    break
                compatibility = True
                remember = getattr(self.client, "remember_plain_json", None)
                if callable(remember):
                    remember(model)
        assert last_error is not None
        raise LocalModelResponseError(
            "The local model did not return usable combat narration after one retry."
        ) from last_error

    @staticmethod
    def _payload(
        *,
        model: str,
        context: dict[str, Any],
        allowed_intents: dict[str, tuple[str, ...]],
        compatibility: bool,
    ) -> dict[str, Any]:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "combat_narration_and_intent",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "narrative_segments": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 4,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": ["narrative", "monologue", "spoken"],
                                    },
                                    "text": {"type": "string", "minLength": 1},
                                },
                                "required": ["kind", "text"],
                                "additionalProperties": False,
                            },
                        },
                        "enemy_intents": {
                            "type": "array",
                            "maxItems": 12,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "combatant_id": {"type": "string"},
                                    "intent": {
                                        "type": "string",
                                        "enum": [
                                            "attack", "ability", "advance", "defend",
                                            "retreat", "surrender",
                                        ],
                                    },
                                },
                                "required": ["combatant_id", "intent"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["narrative_segments", "enemy_intents"],
                    "additionalProperties": False,
                },
            },
        }
        instruction = (
            DUNGEON_MASTER_SYSTEM
            + "Phrase one concise fantasy combat beat from the already-resolved player action. "
            "The supplied numbers and result are authoritative; do not change dice, health, "
            "damage, distance, inventory, conditions, or outcomes. Choose at most one enemy "
            "intent for each supplied combatant ID and choose only from that combatant's "
            "allowed list. Enemy choices should reflect morale, intelligence, injuries, and "
            "position. Do not control the player character, expose hidden statistics, invent "
            "combatants, or add state changes. Return only the required JSON object."
            " Keep all narrative segments to no more than 125 total words."
        )
        if compatibility:
            instruction += " Output only the compact JSON object; do not call tools."
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": instruction},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "resolved_context": context,
                            "allowed_enemy_intents": allowed_intents,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0.2 if compatibility else 0.55,
            "max_tokens": 3000,
            "stream": False,
        }
        if not compatibility:
            payload["response_format"] = response_format
        return payload

    @staticmethod
    def _parse(
        response: dict[str, Any],
        allowed_intents: dict[str, tuple[str, ...]],
    ) -> CombatNarrationOutcome:
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalModelResponseError("Combat response did not contain a message.") from exc
        if not isinstance(message, dict):
            raise LocalModelResponseError("Combat response message was invalid.")
        content = LocalModelClient._message_content(message)  # noqa: SLF001
        result = LocalModelClient._decode_option_json(content)  # noqa: SLF001
        if not isinstance(result, dict):
            raise LocalModelResponseError("Combat response was not a JSON object.")
        raw_segments = result.get("narrative_segments")
        raw_intents = result.get("enemy_intents")
        if not isinstance(raw_segments, list) or not 1 <= len(raw_segments) <= 4:
            raise LocalModelResponseError("Combat narration was not a bounded array.")
        segments: list[NarrativeSegment] = []
        for raw in raw_segments:
            if not isinstance(raw, dict):
                raise LocalModelResponseError("Combat narration segment was invalid.")
            kind = raw.get("kind")
            text = raw.get("text")
            if kind not in {"narrative", "monologue", "spoken"}:
                raise LocalModelResponseError("Combat narration kind was invalid.")
            if not isinstance(text, str) or not text.strip() or len(text) > 1000:
                raise LocalModelResponseError("Combat narration text was invalid.")
            segments.append(NarrativeSegment(str(kind), sanitize_model_text(text)))
        if not isinstance(raw_intents, list) or len(raw_intents) > 12:
            raise LocalModelResponseError("Enemy intents were not a bounded array.")
        intents: dict[str, str] = {}
        for raw in raw_intents:
            if not isinstance(raw, dict):
                raise LocalModelResponseError("Enemy intent entry was invalid.")
            combatant_id = raw.get("combatant_id")
            intent = raw.get("intent")
            if combatant_id not in allowed_intents:
                raise LocalModelResponseError("Enemy intent targeted an unavailable combatant.")
            if not isinstance(intent, str) or intent not in allowed_intents[combatant_id]:
                raise LocalModelResponseError("Enemy intent was not allowed by combat rules.")
            intents[combatant_id] = intent
        return CombatNarrationOutcome(limit_narrative_segments(segments), intents)
