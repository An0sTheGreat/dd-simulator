from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from dd_simulator.local_model import (
    CharacterRandomizationService,
    LocalModelClient,
    LocalModelConnectionError,
    LocalModelResponseError,
)
from dd_simulator.ui.panels.campaign_panels import CharacterCreationPanel
from test_character_creation import unlock_panel, valid_draft


def _profile() -> dict[str, object]:
    return {
        "campaign_name": "Ashes of the Verdant Crown",
        "campaign_description": "A dying forest crown has awakened an old enemy beneath the borderlands.",
        "name": "Mira Thorn",
        "ancestry": "Human",
        "age": 28,
        "gender_identity": "Woman",
        "pronouns": "she/her",
        "body_description": "A lean ranger shaped by long forest patrols.",
        "face_description": "Weathered features, green eyes, and braided dark hair.",
        "clothing_style": "Layered green travel clothes suited to a forest frontier.",
        "background": "Monster hunter",
        "character_class": "Ranger",
        "primary_weapon": "Longsword",
        "secondary_weapon": "Dagger",
        "ranged_weapon": "Longbow",
        "armor": "Leather armor",
        "shield": "None",
        "important_tool": "Navigator's tools",
        "keepsake": "Family locket",
        "personalities": ["Brave", "Cautious"],
        "primary_strength": "Survival instinct",
        "meaningful_flaw": "Distrust",
        "motivation": "Protecting someone",
        "biography": "A border ranger searching for a missing sibling.",
        "backstory": "Mira survived the fall of a forest outpost and followed its trail east.",
        "skills": ["Ranged", "Survival", "Herblore"],
    }


def test_creation_tabs_fields_width_and_compact_spacing() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    unlock_panel(panel)
    panel.resize(1600, 900)
    panel.show()
    app.processEvents()

    assert [
        panel.tabs.tabText(index).replace("&&", "&")
        for index in range(panel.tabs.count())
    ] == [
        "1. Local AI Model Selection",
        "2. Character Sheet",
        "3. Campaign",
        "4. Final Review",
    ]
    character = panel.findChild(QWidget, "characterCreationSheetSurface")
    assert character is not None
    for widget in (
        next(iter(panel.personality_buttons.values())),
        panel.primary_strength, panel.flaw, panel.motivation,
    ):
        assert character.isAncestorOf(widget)
    assert character.isAncestorOf(panel.biography)
    assert character.isAncestorOf(panel.equipment_fields["primary_weapon"])

    page = panel.findChild(QWidget, "campaignCreationPage")
    left_form = panel.findChild(QWidget, "campaignCreationLeftForm")
    right_form = panel.findChild(QWidget, "campaignCreationRightForm")
    assert page is not None and left_form is not None and right_form is not None
    assert left_form.layout().verticalSpacing() == 4
    assert right_form.layout().verticalSpacing() == 4
    assert abs(left_form.parentWidget().width() - right_form.parentWidget().width()) < 60

    panel.close()
    app.processEvents()


def test_focus_skill_buttons_lock_at_three_and_reopen_after_deselect() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    unlock_panel(panel)
    buttons = panel.findChildren(QPushButton, "focusSkillButton")
    assert len(buttons) == 8

    for skill in ("Attack", "Ranged", "Survival"):
        panel.skill_buttons[skill].click()
    assert panel.skill_counter.text() == "3 / 3 selected"
    assert panel.draft().skills == ("Attack", "Ranged", "Survival")
    assert all(
        button.isEnabled() == button.isChecked()
        for button in panel.skill_buttons.values()
    )

    panel.skill_buttons["Ranged"].click()
    assert panel.skill_counter.text() == "2 / 3 selected"
    assert all(button.isEnabled() for button in panel.skill_buttons.values())
    panel.skill_buttons["Magic"].click()
    assert panel.draft().skills == ("Attack", "Survival", "Magic")

    panel.deleteLater()
    app.processEvents()


def test_campaign_generation_changes_only_name_and_premise() -> None:
    class RecordingClient:
        def __init__(self, details: dict[str, object]) -> None:
            self.details = details
            self.context: dict[str, object] = {}

        def generate_campaign_details(self, *, context):  # type: ignore[no-untyped-def]
            self.context = context
            return self.details

    draft = valid_draft(
        world_type="Dark fantasy", tone="Mysterious", difficulty="Veteran",
        content_preferences="No graphic injury; mystery encouraged.",
    )
    client = RecordingClient({
        "campaign_name": "Ashes of the Verdant Crown",
        "campaign_description": "A dying forest crown awakens an old enemy.",
    })
    generated = CharacterRandomizationService(client).generate_campaign(draft)  # type: ignore[arg-type]

    assert generated.name == draft.name
    assert generated.campaign_description.startswith("A dying forest crown")
    for field in draft.__dataclass_fields__:
        if field not in {"campaign_name", "campaign_description"}:
            assert getattr(generated, field) == getattr(draft, field)
    assert client.context["campaign"]["world_type"] == "Dark fantasy"  # type: ignore[index]
    assert client.context["player"]["class"] == draft.character_class  # type: ignore[index]

    with pytest.raises(LocalModelResponseError, match="invalid"):
        invalid = {"campaign_name": 7, "campaign_description": "Valid premise"}
        CharacterRandomizationService(RecordingClient(invalid)).generate_campaign(draft)  # type: ignore[arg-type]


def test_profile_request_and_ui_failure_are_bounded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": json.dumps(_profile())}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr("dd_simulator.local_model.client.urlopen", fake_urlopen)
    assert LocalModelClient(model_id="local").generate_character_profile(
        context={"world_and_safety": {"world_type": "Dark fantasy"}}
    )["name"] == "Mira Thorn"
    payload = captured["payload"]
    assert payload["response_format"]["json_schema"]["name"] == "character_creation_profile"  # type: ignore[index]
    assert payload["max_tokens"] == 3000  # type: ignore[index]

    class OfflineRandomizer:
        def generate_campaign(self, _draft):  # type: ignore[no-untyped-def]
            raise LocalModelConnectionError("LM Studio is offline")

    class ImmediatePool:
        def start(self, task):  # type: ignore[no-untyped-def]
            task.run()

    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel(
        OfflineRandomizer(), thread_pool=ImmediatePool()  # type: ignore[arg-type]
    )
    unlock_panel(panel)
    panel.campaign_name.setText("Keep This Campaign")
    panel._request_campaign_randomization()
    assert panel.campaign_name.text() == "Keep This Campaign"
    assert panel.randomize_campaign_button.isEnabled()
    assert panel.error_label.text() == "LM Studio is offline"
    panel.deleteLater()
    app.processEvents()


def test_campaign_and_intro_requests_use_plain_json_dm_prompts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payloads: list[dict[str, object]] = []

    class Response:
        def __init__(self, value: dict[str, str]) -> None:
            self.value = value

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": json.dumps(self.value)}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        payload = json.loads(request.data.decode("utf-8"))
        payloads.append(payload)
        if "CAMPAIGN PREMISE" in payload["messages"][0]["content"]:
            return Response({
                "campaign_name": "Crown of Embers",
                "campaign_description": "An ember crown draws rivals to the frontier.",
            })
        return Response({"introduction": "Dawn finds the ranger at the frontier gate."})

    monkeypatch.setattr("dd_simulator.local_model.client.urlopen", fake_urlopen)
    client = LocalModelClient(model_id="local")
    details = client.generate_campaign_details(context={"player": {"name": "Aria"}})
    intro = client.generate_campaign_introduction(
        context={"campaign": details, "player": {"name": "Aria"}}
    )

    assert details["campaign_name"] == "Crown of Embers"
    assert intro.startswith("Dawn finds")
    assert all("response_format" not in payload for payload in payloads)
    assert all(
        "Dungeon Master" in payload["messages"][0]["content"]  # type: ignore[index]
        for payload in payloads
    )


def test_generated_campaign_populates_form_without_overwriting_world() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    panel.world_type.setCurrentText("Dark fantasy")
    panel.tone.setCurrentText("Mysterious")
    panel.character_name.setText("Keep My Character")
    generated = valid_draft(
        campaign_name="Ashes of the Verdant Crown", name="Mira Thorn",
        skills=("Ranged", "Survival", "Herblore"),
        personalities=("Brave", "Cautious"),
    )

    panel._apply_generated_campaign(generated)

    assert panel.campaign_name.text() == "Ashes of the Verdant Crown"
    assert panel.campaign_description.toPlainText() == generated.campaign_description
    assert panel.character_name.text() == "Keep My Character"
    assert panel.draft().skills == ()
    assert panel.world_type.currentText() == "Dark fantasy"
    assert panel.tone.currentText() == "Mysterious"
    panel.deleteLater()
    app.processEvents()


def test_appearance_randomization_context_contains_world_and_safety() -> None:
    class RecordingClient:
        def __init__(self) -> None:
            self.context: dict[str, object] = {}

        def generate_options(self, *, section, context):  # type: ignore[no-untyped-def]
            assert section == "face_description"
            self.context = context
            return ("one", "two", "three")

    client = RecordingClient()
    service = CharacterRandomizationService(client)  # type: ignore[arg-type]
    service.generate_options(
        "face_description",
        valid_draft(
            world_type="Gothic horror", tone="Dark",
            content_preferences="No graphic injury.",
        ),
    )
    assert client.context["world_type"] == "Gothic horror"
    assert client.context["tone"] == "Dark"
    assert client.context["content_preferences"] == "No graphic injury."
