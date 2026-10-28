"""Optional local model phrasing for already-resolved NPC dialogue facts."""

from __future__ import annotations

import json
import logging
from typing import Any

from dd_simulator.local_model.client import LocalModelClient
from dd_simulator.local_model.errors import LocalModelError, LocalModelResponseError
from dd_simulator.local_model.prompts import DUNGEON_MASTER_SYSTEM
from dd_simulator.state.turns import limit_words, sanitize_model_text
from dd_simulator.state.dialogue import DialogueNarration


LOGGER = logging.getLogger(__name__)


class LocalModelDialogueNarrator:
    def __init__(self, client: LocalModelClient) -> None:
        self.client = client

    def phrase_dialogue(self, *, context: dict[str, object]) -> DialogueNarration:
        selector = getattr(self.client, "preferred_model_id", None)
        model = selector() if callable(selector) else self.client.model_id or self.client.discover_models()[0]
        last_error: LocalModelError | None = None
        model_reported_unloaded = False
        checker = getattr(self.client, "uses_plain_json", None)
        starts_plain = bool(checker(model)) if callable(checker) else False
        modes = ("json", "prose") if starts_plain else ("schema", "json", "prose")
        for attempt, mode in enumerate(modes):
            try:
                response = self.client._json_request(  # noqa: SLF001
                    "/chat/completions",
                    method="POST",
                    payload=self._payload(
                        model=model,
                        context=context,
                        mode=mode,
                    ),
                )
                return self._parse(response, allow_plain_text=mode == "prose")
            except LocalModelError as exc:
                last_error = exc
                LOGGER.warning(
                    "Local model dialogue response rejected: model=%s attempt=%s reason=%s",
                    model,
                    attempt + 1,
                    exc,
                )
                if not LocalModelClient.supports_schema_fallback(exc):
                    break
                remember = getattr(self.client, "remember_plain_json", None)
                if mode == "schema" and callable(remember):
                    remember(model)
                if "channel error" in str(exc).casefold():
                    loaded = getattr(self.client, "is_model_loaded", None)
                    if callable(loaded) and not loaded(model):
                        model_reported_unloaded = True
        assert last_error is not None
        if model_reported_unloaded:
            raise LocalModelResponseError(
                "The selected local model appears to be unloaded. Reload it in Settings."
            ) from last_error
        raise LocalModelResponseError(
            "The local model did not return usable NPC dialogue after bounded compatibility recovery. "
            f"Last response: {last_error}"
        ) from last_error

    @staticmethod
    def _payload(
        *,
        model: str,
        context: dict[str, object],
        mode: str,
    ) -> dict[str, Any]:
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "npc_dialogue",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "speech": {"type": "string", "minLength": 1, "maxLength": 2000},
                        "monologue": {"type": "string", "maxLength": 1000},
                        "quest_offer": {
                            "anyOf": [
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "summary": {"type": "string"},
                                        "objectives": {
                                            "type": "array", "minItems": 2, "maxItems": 5,
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "text": {"type": "string"},
                                                    "optional": {"type": "boolean"},
                                                    "trigger_type": {"type": "string"},
                                                    "trigger_target": {"type": "string"},
                                                },
                                                "required": ["text", "optional", "trigger_type", "trigger_target"],
                                                "additionalProperties": False,
                                            },
                                        },
                                    },
                                    "required": ["title", "summary", "objectives"],
                                    "additionalProperties": False,
                                },
                            ]
                        },
                    },
                    "required": ["speech", "monologue", "quest_offer"],
                    "additionalProperties": False,
                },
            },
        }
        instruction = (
            DUNGEON_MASTER_SYSTEM
            + "Write the NPC's direct response to the player's latest words and one brief "
            "internal or visual reaction. Continue the supplied recent conversation instead "
            "of repeating an earlier reply. Use only supplied facts, memories, personality, "
            "status, relationship, quests, location, and resolved check outcome. Never invent "
            "rewards, mechanical changes, locations, routes, facts, or a different check result. "
            "If and only if the NPC clearly offers the player a concrete task in this reply, "
            "include quest_offer with a concise title, summary, and 2 to 5 grounded objectives; "
            "otherwise set quest_offer to null. Objectives may use trigger_type combat, travel, "
            "item_collect, item_use, item_examine, dialogue, or custom_action, and must identify "
            "their visible target in trigger_target. Speech and monologue together must not exceed "
            "125 words. Return JSON with speech, monologue, and quest_offer."
        )
        if mode == "json":
            instruction += (
                " This is a compatibility retry. Output only this compact shape without "
                "Markdown or reasoning: {\"speech\":\"...\",\"monologue\":\"...\","
                "\"quest_offer\":null}."
            )
        elif mode == "prose":
            instruction = (
                DUNGEON_MASTER_SYSTEM
                + "Reply as the supplied NPC to the player's latest words. Continue the recent "
                "conversation using only supplied facts. Output plain prose only, at most 125 "
                "words. Do not emit JSON, tools, rewards, quests, or mechanical changes."
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            "temperature": 0.25 if mode == "json" else 0.8,
            "max_tokens": 900,
            "stream": False,
        }
        if mode == "schema":
            payload["response_format"] = response_format
        return payload

    @staticmethod
    def _parse(
        response: dict[str, Any],
        *,
        allow_plain_text: bool,
    ) -> DialogueNarration:
        try:
            content = LocalModelClient._message_content(response["choices"][0]["message"])  # noqa: SLF001
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalModelResponseError("Dialogue response did not contain a message.") from exc
        try:
            parsed = LocalModelClient._decode_option_json(content)  # noqa: SLF001
        except LocalModelResponseError:
            if allow_plain_text and isinstance(content, str):
                speech = sanitize_model_text(content)
                if speech and len(speech) <= 2000:
                    return DialogueNarration(limit_words(speech, 125), "")
            raise
        if isinstance(parsed, dict):
            for wrapper in ("npc_dialogue", "dialogue", "result", "response"):
                nested = parsed.get(wrapper)
                if isinstance(nested, dict):
                    parsed = nested
                    break
        if not isinstance(parsed, dict):
            raise LocalModelResponseError("Dialogue response did not match the required schema.")
        speech = next(
            (
                parsed[key]
                for key in ("speech", "npc_text", "reply", "response_text")
                if isinstance(parsed.get(key), str) and str(parsed[key]).strip()
            ),
            "",
        )
        monologue = next(
            (
                parsed[key]
                for key in ("monologue", "reaction", "inner_monologue", "narration")
                if isinstance(parsed.get(key), str)
            ),
            "",
        )
        quest_offer = parsed.get("quest_offer")
        if quest_offer is not None and not isinstance(quest_offer, dict):
            quest_offer = None
        speech = sanitize_model_text(str(speech))
        monologue = sanitize_model_text(str(monologue))
        if not speech or len(speech) > 2000 or len(monologue) > 1000:
            raise LocalModelResponseError("Dialogue response did not match the required schema.")
        speech = limit_words(speech, 125)
        remaining = max(0, 125 - len(speech.split()))
        return DialogueNarration(
            speech,
            limit_words(monologue, remaining) if remaining else "",
            quest_offer,
        )
