from __future__ import annotations

import json
import os
from urllib.error import URLError

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QSignalSpy

from dd_simulator.lm_studio import (
    CharacterRandomizationService,
    LMStudioClient,
    LMStudioConnectionError,
    LMStudioResponseError,
    LMStudioActionResolver,
    LMStudioCombatNarrator,
)
from dd_simulator.ui.services.randomization_worker import RandomizationTask
from test_character_creation import valid_draft


class FakeResponse:
    def __init__(self, value: object) -> None:
        self.payload = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_client_rejects_non_local_endpoints() -> None:
    with pytest.raises(ValueError, match="localhost"):
        LMStudioClient("https://example.com/v1")
    with pytest.raises(ValueError, match="end at /v1"):
        LMStudioClient("http://localhost:1234/api")


def test_client_discovers_model_and_requests_plain_json_options(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured[request.full_url] = timeout
        if request.full_url.endswith("/models"):
            return FakeResponse({"data": [{"id": "local-model"}]})
        payload = json.loads(request.data.decode("utf-8"))
        captured["payload"] = payload
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"options": ["Raised on the frontier", "A court exile", "A quiet scholar"]}
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("dd_simulator.lm_studio.client.urlopen", fake_urlopen)
    client = LMStudioClient(timeout_seconds=7)
    options = client.generate_options(
        section="biography",
        context={"name": "Aria", "content_preferences": "No graphic injury"},
    )

    assert options == ("Raised on the frontier", "A court exile", "A quiet scholar")
    payload = captured["payload"]
    assert payload["model"] == "local-model"  # type: ignore[index]
    assert payload["stream"] is False  # type: ignore[index]
    assert "response_format" not in payload
    user_context = json.loads(payload["messages"][1]["content"])  # type: ignore[index]
    assert user_context["requested_section"] == "biography"
    assert user_context["character_context"]["name"] == "Aria"


@pytest.mark.parametrize(
    "content",
    [
        "```json\n{\"options\":[\"one\",\"two\",\"three\"]}\n```",
        "Generated choices: {\"suggestions\":[\"one\",\"two\",\"three\"]}",
        ["one", "two", "three"],
        [{"type": "text", "text": "{\"options\":[\"one\",\"two\",\"three\"]}"}],
        json.dumps({
            "options": [
                {"text": "one"},
                {"option": "two"},
                {"title": "three"},
            ]
        }),
        "1. one\n2) two\n- three",
    ],
)
def test_client_accepts_safe_common_response_variants(monkeypatch, content) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr("dd_simulator.lm_studio.client.urlopen", fake_urlopen)

    options = LMStudioClient(model_id="model").generate_options(
        section="face_description", context={}
    )

    assert options == ("one", "two", "three")
    assert calls == 1


def test_client_retries_once_with_field_specific_instruction(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payloads: list[dict[str, object]] = []

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 30.0
        payloads.append(json.loads(request.data.decode("utf-8")))
        if len(payloads) == 1:
            return FakeResponse(
                {"choices": [{"message": {"content": "I generated three ideas."}}]}
            )
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": {
                                "options": ["retry one", "retry two", "retry three"]
                            }
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("dd_simulator.lm_studio.client.urlopen", fake_urlopen)

    options = LMStudioClient(model_id="model").generate_options(
        section="face_description", context={"name": "Aria"}
    )

    assert options == ("retry one", "retry two", "retry three")
    assert len(payloads) == 2
    assert payloads[0]["temperature"] == 0.6
    assert payloads[1]["temperature"] == 0.2
    retry_instruction = payloads[1]["messages"][0]["content"]  # type: ignore[index]
    assert "correction retry" in retry_instruction
    assert "facial structure" in retry_instruction


def test_client_retry_failure_is_bounded_and_diagnostics_are_sanitized(
    monkeypatch, caplog
) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse(
            {
                "choices": [
                    {"message": {"content": "private-character-text without JSON"}}
                ]
            }
        )

    monkeypatch.setattr("dd_simulator.lm_studio.client.urlopen", fake_urlopen)

    with pytest.raises(LMStudioResponseError, match="after one retry"):
        LMStudioClient(model_id="model").generate_options(
            section="clothing_style", context={"private": "secret-context"}
        )

    assert calls == 2
    assert "private-character-text" not in caplog.text
    assert "secret-context" not in caplog.text
    assert "attempt=1" in caplog.text
    assert "attempt=2" in caplog.text


def test_client_accepts_tool_call_arguments_without_visible_content(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "function": {
                                "name": "return_options",
                                "arguments": json.dumps({
                                    "options": [
                                        "Height: 6 feet; Build: lean and long-limbed",
                                        "Height: 5 feet 8 inches; Build: broad and sturdy",
                                        "Height: 5 feet 3 inches; Build: compact and agile",
                                    ]
                                }),
                            }
                        }],
                    }
                }]
            }
        ),
    )
    assert LMStudioClient(model_id="model").generate_options(
        section="body_description", context={}
    ) == (
        "Height: 6 feet; Build: lean and long-limbed",
        "Height: 5 feet 8 inches; Build: broad and sturdy",
        "Height: 5 feet 3 inches; Build: compact and agile",
    )


def test_generated_option_limits_and_name_cleanup() -> None:
    response = lambda values: {  # noqa: E731
        "choices": [{"message": {"content": json.dumps({"options": values})}}]
    }
    assert LMStudioClient._parse_options(
        response([
            '1. **Campaign Name: "Crown of Embers"**',
            "2) The Silent Frontier",
            "- Ashes Beneath Dawn",
        ]),
        section="campaign_name",
    ) == ("Crown of Embers", "The Silent Frontier", "Ashes Beneath Dawn")
    with pytest.raises(LMStudioResponseError, match="oversized"):
        LMStudioClient._parse_options(
            response(["word " * 76, "A valid second appearance", "A valid third appearance"]),
            section="body_description",
        )
    with pytest.raises(LMStudioResponseError, match="oversized"):
        LMStudioClient._parse_options(
            response(["first", "second", "third"]), section="clothing_style"
        )
    with pytest.raises(LMStudioResponseError, match="Height and Build"):
        LMStudioClient._parse_options(
            response([
                "A mage reads beside the fire",
                "A ranger checks a bow",
                "A rogue watches the door",
            ]),
            section="body_description",
        )


def test_campaign_details_accept_labeled_text_and_nested_json() -> None:
    response = lambda content: {  # noqa: E731
        "choices": [{"message": {"content": content}}]
    }
    assert LMStudioClient._parse_campaign_details(response(
        "CAMPAIGN NAME: Crown of Embers\n"
        "CAMPAIGN PREMISE: Rival heirs hunt an ember crown on the frontier."
    )) == {
        "campaign_name": "Crown of Embers",
        "campaign_description": "Rival heirs hunt an ember crown on the frontier.",
    }
    assert LMStudioClient._parse_campaign_details(response(json.dumps({
        "campaign": {
            "title": "The Silent Frontier",
            "premise": {"text": "A vanished patrol exposes an ancient border pact."},
        }
    }))) == {
        "campaign_name": "The Silent Frontier",
        "campaign_description": "A vanished patrol exposes an ancient border pact.",
    }


def test_campaign_details_accept_unlabeled_premise_without_overwriting_name() -> None:
    response = {
        "choices": [{"message": {"content": (
            "A vanished patrol draws the hero into an ancient forest conspiracy. "
            "The first clues wait at the border tavern."
        )}}]
    }

    labeled = {
        "choices": [{"message": {"content": (
            "CAMPAIGN PREMISE: A sealed gate beneath the village begins to wake."
        )}}]
    }
    assert LMStudioClient._parse_campaign_details(
        labeled, fallback_name="The Silent Frontier"
    ) == {
        "campaign_name": "The Silent Frontier",
        "campaign_description": "A sealed gate beneath the village begins to wake.",
    }
    assert LMStudioClient._parse_campaign_details(
        response, fallback_name="The Silent Frontier"
    ) == {
        "campaign_name": "The Silent Frontier",
        "campaign_description": (
            "A vanished patrol draws the hero into an ancient forest conspiracy. "
            "The first clues wait at the border tavern."
        ),
    }


def test_campaign_details_accept_short_title_line_before_unlabeled_premise() -> None:
    response = {
        "choices": [{"message": {"content": (
            "Crown of Embers\nRival heirs hunt an ember crown across the frontier."
        )}}]
    }
    assert LMStudioClient._parse_campaign_details(response) == {
        "campaign_name": "Crown of Embers",
        "campaign_description": "Rival heirs hunt an ember crown across the frontier.",
    }


def test_campaign_introduction_is_capped_at_220_words() -> None:
    response = {
        "choices": [{"message": {"content": json.dumps({
            "introduction": "word " * 240,
        })}}]
    }
    assert len(LMStudioClient._parse_introduction(response).split()) == 220


def test_loading_a_model_unloads_other_active_instances(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = LMStudioClient(model_id="old")
    requests: list[tuple[str, str, object]] = []

    def fake_request(url, *, method="GET", payload=None, timeout_seconds=None):  # type: ignore[no-untyped-def]
        requests.append((url, method, payload))
        if url.endswith("/api/v1/models"):
            return {
                "models": [
                    {"key": "old", "loaded_instances": [{"id": "old-instance"}]},
                    {"key": "target", "loaded_instances": []},
                ]
            }
        if url.endswith("/unload"):
            return {"status": "unloaded"}
        if url.endswith("/load"):
            return {"status": "loaded", "instance_id": "target-instance"}
        raise AssertionError(url)

    monkeypatch.setattr(client, "_json_request_url", fake_request)
    assert client.load_exclusive_model("target") == "target-instance"
    assert any(
        url.endswith("/unload") and payload == {"instance_id": "old-instance"}
        for url, _method, payload in requests
    )


def test_client_preserves_fields_on_connection_and_schema_failures(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    with pytest.raises(LMStudioConnectionError, match="localhost:1234"):
        LMStudioClient(model_id="model").generate_options(
            section="backstory", context={}
        )

    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {
                "choices": [
                    {"message": {"content": json.dumps({"options": ["same", "same", "same"]})}}
                ]
            }
        ),
    )
    with pytest.raises(LMStudioResponseError, match="duplicate"):
        LMStudioClient(model_id="model").generate_options(
            section="backstory", context={}
        )


def test_randomizer_sends_bounded_current_character_context() -> None:
    class RecordingClient:
        def __init__(self) -> None:
            self.section = ""
            self.context: dict[str, object] = {}

        def generate_options(self, *, section: str, context: dict[str, object]):
            self.section = section
            self.context = context
            return ("one", "two", "three")

    client = RecordingClient()
    service = CharacterRandomizationService(client)  # type: ignore[arg-type]
    assert service.generate_options("backstory", valid_draft()) == (
        "one", "two", "three"
    )
    assert client.section == "biography"
    assert client.context["ancestry"] == "Human"
    assert client.context["class_or_archetype"] == "Ranger"
    assert client.context["personality_traits"] == ["Brave", "Curious"]
    assert client.context["campaign_name"] == "Northern Lights"
    assert "wandering ranger" in str(client.context["biography_backstory"]).casefold()


def test_randomization_worker_reports_failure_and_completion() -> None:
    class OfflineRandomizer:
        def generate_options(self, _section, _draft):  # type: ignore[no-untyped-def]
            raise LMStudioConnectionError("offline")

    task = RandomizationTask(OfflineRandomizer(), "biography", valid_draft())  # type: ignore[arg-type]
    failed = QSignalSpy(task.signals.failed)
    finished = QSignalSpy(task.signals.finished)
    succeeded = QSignalSpy(task.signals.succeeded)

    task.run()

    assert failed.count() == 1
    assert failed.at(0) == ["biography", "offline"]
    assert finished.at(0) == ["biography"]
    assert succeeded.count() == 0


def valid_turn_content(*, operation: str | None = None) -> dict[str, object]:
    changes: list[dict[str, object]] = []
    if operation is not None:
        changes.append(
            {
                "operation": operation,
                "target_type": "resource",
                "target_id": "resource-stamina",
                "field": "current_value",
                "value": 2,
                "reason": "The action requires effort.",
            }
        )
    return {
        "narrative_segments": [
            {"kind": "narrative", "text": "The character studies the road ahead."},
            {"kind": "monologue", "text": "The stones may hide a clue."},
            {"kind": "spoken", "text": "The path is clear."},
        ],
        "state_changes": changes,
        "quest_notes": [],
        "memory_candidates": [],
        "suggested_actions": [
            "Continue forward",
            "Inspect the road",
            "Listen carefully",
            "Check the stones",
            "Return to the merchant",
            "Rest briefly",
        ],
    }


def test_action_resolver_requests_strict_bounded_turn_schema(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            {"choices": [{"message": {"content": json.dumps(valid_turn_content(operation="spend_resource"))}}]}
        )

    monkeypatch.setattr("dd_simulator.lm_studio.client.urlopen", fake_urlopen)
    resolver = LMStudioActionResolver(LMStudioClient(model_id="model", timeout_seconds=9))

    result = resolver.resolve_action(
        action="climb the wall",
        context={"allowed_targets": {"resource_ids": ["resource-stamina"]}},
    )

    assert result.narration.startswith("The character")
    assert tuple(segment.kind for segment in result.narrative_segments) == (
        "narrative", "monologue", "spoken"
    )
    assert result.state_changes[0].operation == "spend_resource"
    payload = captured["payload"]
    assert payload["response_format"]["json_schema"]["name"] == "non_combat_turn_result"  # type: ignore[index]
    assert payload["stream"] is False  # type: ignore[index]
    user_data = json.loads(payload["messages"][1]["content"])  # type: ignore[index]
    assert user_data["player_action"] == "climb the wall"
    assert "untrusted game data" in payload["messages"][0]["content"]  # type: ignore[index]
    assert "equippable_inventory_item_ids" in payload["messages"][0]["content"]  # type: ignore[index]


def test_action_resolver_caps_narrative_segments_at_125_words() -> None:
    raw = valid_turn_content()
    raw["narrative_segments"] = [
        {"kind": "narrative", "text": "word " * 150},
        {"kind": "spoken", "text": "more " * 20},
    ]
    response = {"choices": [{"message": {"content": json.dumps(raw)}}]}
    result = LMStudioActionResolver._parse(response)
    assert sum(len(segment.text.split()) for segment in result.narrative_segments) == 125


def test_action_resolver_accepts_wrapped_json_and_retries_once(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payloads: list[dict[str, object]] = []

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 30.0
        payloads.append(json.loads(request.data.decode("utf-8")))
        if len(payloads) == 1:
            return FakeResponse({"choices": [{"message": {"content": ""}}]})
        wrapped = "```json\n" + json.dumps({"turn_result": valid_turn_content()}) + "\n```"
        return FakeResponse({"choices": [{"message": {"content": wrapped}}]})

    monkeypatch.setattr("dd_simulator.lm_studio.client.urlopen", fake_urlopen)

    result = LMStudioActionResolver(LMStudioClient(model_id="model")).resolve_action(
        action="listen",
        context={},
    )

    assert len(result.suggested_actions) == 6
    assert len(payloads) == 2
    assert payloads[1]["temperature"] == 0.2
    assert "format correction retry" in payloads[1]["messages"][0]["content"]  # type: ignore[index]


def test_action_resolver_remembers_plain_json_after_schema_channel_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from dd_simulator.lm_studio.errors import LMStudioConnectionError

    client = LMStudioClient(model_id="model")
    payloads: list[dict[str, object]] = []

    def request(_path, *, method="GET", payload=None):  # type: ignore[no-untyped-def]
        assert method == "POST"
        payloads.append(payload)
        if len(payloads) == 1:
            raise LMStudioConnectionError("LM Studio returned HTTP 400. Channel Error")
        return {
            "choices": [{"message": {"content": json.dumps(valid_turn_content())}}]
        }

    monkeypatch.setattr(client, "_json_request", request)
    resolver = LMStudioActionResolver(client)
    resolver.resolve_action(action="listen", context={})
    resolver.resolve_action(action="wait", context={})

    assert "response_format" in payloads[0]
    assert "response_format" not in payloads[1]
    assert "response_format" not in payloads[2]


def test_action_resolver_keeps_narration_and_drops_unknown_operations_without_logging_content(
    monkeypatch, caplog
) -> None:  # type: ignore[no-untyped-def]
    raw = valid_turn_content(operation="delete_database")
    raw["narrative_segments"] = [
        {"kind": "narrative", "text": "private narration marker"}
    ]
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"choices": [{"message": {"content": json.dumps(raw)}}]}
        ),
    )

    result = LMStudioActionResolver(LMStudioClient(model_id="model")).resolve_action(
        action="private action marker",
        context={"private": "private context marker"},
    )

    assert result.narration == "private narration marker"
    assert result.state_changes == ()
    assert "private narration marker" not in caplog.text
    assert "private action marker" not in caplog.text
    assert "private context marker" not in caplog.text


def test_action_resolver_accepts_plain_narration_and_builds_local_suggestions(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"choices": [{"message": {"content": "The barmaid offers ale and stew."}}]}
        ),
    )

    result = LMStudioActionResolver(LMStudioClient(model_id="model")).resolve_action(
        action="Ask the barmaid about her wares",
        context={},
    )

    assert result.narration == "The barmaid offers ale and stew."
    assert len(result.suggested_actions) == 6


def test_action_resolver_accepts_alternate_suggestion_shapes_and_removes_placeholders() -> None:
    raw = valid_turn_content()
    del raw["suggested_actions"]
    raw["options"] = {
        "first": {"text": "Ask about the ale"},
        "second": {"label": "Ask about the stew"},
        "third": "suggested_actions_2",
    }

    result = LMStudioActionResolver._sanitize_suggestions(
        LMStudioActionResolver._parse(
            {"choices": [{"message": {"content": json.dumps(raw)}}]}
        ),
        {},
    )

    assert result.suggested_actions[:2] == ("Ask about the ale", "Ask about the stew")
    assert "suggested_actions_2" not in result.suggested_actions
    assert len(result.suggested_actions) == 6


def test_action_resolver_accepts_valid_examine_and_equippable_item_targets(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    raw = valid_turn_content()
    raw["state_changes"] = [
        {
            "operation": "examine_item",
            "target_type": "inventory_item",
            "target_id": "item-letter",
            "field": None,
            "value": "unnecessary model detail",
            "reason": "The player examines the letter.",
        },
        {
            "operation": "equip_item",
            "target_type": "inventory_item",
            "target_id": "item-sword",
            "field": None,
            "value": True,
            "reason": "The player equips the sword.",
        },
    ]
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"choices": [{"message": {"content": json.dumps(raw)}}]}
        ),
    )
    context = {
        "inventory": [
            {"id": "item-letter", "name": "Merchant Letter"},
            {"id": "item-sword", "name": "Longsword"},
        ],
        "allowed_targets": {
            "examinable_inventory_item_ids": ["item-letter", "item-sword"],
            "equippable_inventory_item_ids": ["item-sword"],
        },
    }

    result = LMStudioActionResolver(LMStudioClient(model_id="model")).resolve_action(
        action="Examine the letter and equip the Longsword",
        context=context,
    )

    assert tuple(change.operation for change in result.state_changes) == (
        "examine_item", "equip_item"
    )
    assert tuple(change.value for change in result.state_changes) == (True, True)


def test_action_resolver_recovers_explicit_examine_omitted_by_model(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    raw = valid_turn_content()
    raw["state_changes"] = []
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"choices": [{"message": {"content": json.dumps(raw)}}]}
        ),
    )
    context = {
        "inventory": [{"id": "item-letter", "name": "Merchant Letter"}],
        "allowed_targets": {
            "examinable_inventory_item_ids": ["item-letter"],
        },
    }

    result = LMStudioActionResolver(LMStudioClient(model_id="model")).resolve_action(
        action="Read the Merchant Letter closely",
        context=context,
    )

    assert len(result.state_changes) == 1
    assert result.state_changes[0].operation == "examine_item"
    assert result.state_changes[0].target_id == "item-letter"


@pytest.mark.parametrize(
    "suggestion",
    (
        "Examine item-13 closely",
        "Equip the Map Fragment",
    ),
)
def test_action_resolver_sanitizes_internal_ids_and_impossible_equip_suggestions(
    monkeypatch,
    suggestion: str,
) -> None:  # type: ignore[no-untyped-def]
    raw = valid_turn_content()
    raw["suggested_actions"][0] = suggestion  # type: ignore[index]
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"choices": [{"message": {"content": json.dumps(raw)}}]}
        ),
    )
    context = {
        "inventory": [{"id": "item-3", "name": "Map Fragment"}],
        "allowed_targets": {
            "equippable_inventory_item_ids": [],
        },
    }

    result = LMStudioActionResolver(LMStudioClient(model_id="model")).resolve_action(
        action="look around",
        context=context,
    )

    assert len(result.suggested_actions) == 6
    assert all("item-" not in action.lower() for action in result.suggested_actions)
    assert all(not action.lower().startswith("equip") for action in result.suggested_actions)


def test_combat_narrator_accepts_only_allowed_enemy_intents(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    raw = {
        "narrative_segments": [
            {"kind": "narrative", "text": "The goblin circles the damaged cart."}
        ],
        "enemy_intents": [
            {"combatant_id": "combatant-goblin", "intent": "advance"}
        ],
    }
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"choices": [{"message": {"content": json.dumps(raw)}}]}
        ),
    )

    result = LMStudioCombatNarrator(
        LMStudioClient(model_id="model")
    ).resolve_combat_turn(
        context={"resolved_player_action": "The player defended."},
        allowed_intents={"combatant-goblin": ("advance", "defend")},
    )

    assert result.enemy_intents == {"combatant-goblin": "advance"}
    assert result.narrative_segments[0].kind == "narrative"


def test_combat_narrator_rejects_mechanical_or_unavailable_intent(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    raw = {
        "narrative_segments": [{"kind": "narrative", "text": "A blow lands."}],
        "enemy_intents": [
            {"combatant_id": "combatant-goblin", "intent": "deal_999_damage"}
        ],
    }
    monkeypatch.setattr(
        "dd_simulator.lm_studio.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"choices": [{"message": {"content": json.dumps(raw)}}]}
        ),
    )

    with pytest.raises(LMStudioResponseError, match="after one retry"):
        LMStudioCombatNarrator(
            LMStudioClient(model_id="model")
        ).resolve_combat_turn(
            context={},
            allowed_intents={"combatant-goblin": ("attack", "defend")},
        )
