"""Optional LM Studio prose for mechanically resolved travel and camping."""

from __future__ import annotations

import json
from typing import Any

from dd_simulator.lm_studio.client import LMStudioClient
from dd_simulator.lm_studio.errors import LMStudioError, LMStudioResponseError
from dd_simulator.lm_studio.prompts import DUNGEON_MASTER_SYSTEM
from dd_simulator.state.turns import limit_words, sanitize_model_text


class LMStudioTravelNarrator:
    """Return prose only; route, time, costs, danger, and outcomes stay local."""

    def __init__(self, client: LMStudioClient) -> None:
        self.client = client

    def narrate_travel(self, context: dict[str, object]) -> str:
        return self._request("journey and arrival", context)

    def narrate_camp(self, context: dict[str, object]) -> str:
        return self._request("camp and recovery", context)

    def _request(self, scene_type: str, context: dict[str, object]) -> str:
        model = self.client.preferred_model_id()
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "travel_narration",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "narration": {"type": "string", "minLength": 1, "maxLength": 1200}
                    },
                    "required": ["narration"],
                    "additionalProperties": False,
                },
            },
        }
        checker = getattr(self.client, "uses_plain_json", None)
        compatibility = bool(checker(model)) if callable(checker) else False
        last_error: LMStudioError | None = None
        for attempt in range(2):
            instruction = (
                DUNGEON_MASTER_SYSTEM
                + f"Write one concise fantasy {scene_type} paragraph using only the "
                "supplied resolved facts. Do not change the destination, duration, "
                "distance, resource costs, danger, recovery, encounter result, clock, "
                "inventory, quests, or any other game state. Return only JSON with one "
                "narration field using no more than 125 words."
            )
            payload: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": instruction},
                    {
                        "role": "user",
                        "content": json.dumps(context, ensure_ascii=False),
                    },
                ],
                "temperature": 0.2 if compatibility else 0.55,
                "max_tokens": 500,
                "stream": False,
            }
            if not compatibility:
                payload["response_format"] = response_format
            try:
                response = self.client._json_request(  # noqa: SLF001
                    "/chat/completions", method="POST", payload=payload
                )
                return self._parse(response)
            except LMStudioError as exc:
                last_error = exc
                if attempt or not LMStudioClient.supports_schema_fallback(exc):
                    break
                compatibility = True
                remember = getattr(self.client, "remember_plain_json", None)
                if callable(remember):
                    remember(model)
        assert last_error is not None
        raise LMStudioResponseError(
            "LM Studio did not return usable travel narration after one compatibility retry."
        ) from last_error

    @staticmethod
    def _parse(response: dict[str, Any]) -> str:
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LMStudioResponseError("Travel response did not contain a message.") from exc
        content = LMStudioClient._message_content(message)  # noqa: SLF001
        parsed = LMStudioClient._decode_option_json(content)  # noqa: SLF001
        narration = parsed.get("narration") if isinstance(parsed, dict) else None
        if not isinstance(narration, str) or not narration.strip():
            raise LMStudioResponseError("Travel response did not contain narration.")
        return limit_words(sanitize_model_text(narration), 125)
