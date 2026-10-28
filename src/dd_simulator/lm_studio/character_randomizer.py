"""Bounded prompt context for character-creation randomization."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from dd_simulator.lm_studio.client import LMStudioClient
from dd_simulator.lm_studio.errors import LMStudioResponseError
from dd_simulator.state.character_creation import (
    DEFAULT_CONTENT_PREFERENCES,
    CharacterCreationDraft,
)
from dd_simulator.state.presets import preset_fallback_intro, preset_intro_context


class CharacterRandomizationService:
    def __init__(self, client: LMStudioClient) -> None:
        self.client = client

    def generate_options(
        self,
        section: str,
        draft: CharacterCreationDraft,
    ) -> tuple[str, str, str]:
        section = "biography" if section == "backstory" else section
        biography_backstory = " ".join(
            value.strip() for value in (draft.biography, draft.backstory) if value.strip()
        )
        context: dict[str, Any] = {
            "campaign_name": draft.campaign_name,
            "campaign_description": draft.campaign_description,
            "name": draft.name,
            "ancestry": draft.ancestry,
            "adult_age": draft.age,
            "gender_identity": draft.gender_identity,
            "pronouns": draft.pronouns,
            "body_and_height": draft.body_description,
            "face_and_features": draft.face_description,
            "clothing_style": draft.clothing_style,
            "background": draft.background,
            "class_or_archetype": draft.character_class,
            "ability_scores": dict(draft.ability_scores),
            "personality_traits": list(draft.personalities),
            "primary_strength": draft.primary_strength,
            "meaningful_flaw": draft.meaningful_flaw,
            "motivation": draft.motivation,
            "biography_backstory": biography_backstory,
            "focus_skills": list(draft.skills),
            "world_type": draft.world_type,
            "tone": draft.tone,
            "starting_region": draft.starting_region,
            "starting_location": draft.starting_location,
            "difficulty": draft.difficulty,
            "content_preferences": (
                draft.content_preferences.strip() or DEFAULT_CONTENT_PREFERENCES
            ),
            "visual_style": draft.visual_style,
            "camera_style": draft.camera_style,
        }
        return self.client.generate_options(section=section, context=context)

    def generate_campaign(self, draft: CharacterCreationDraft) -> CharacterCreationDraft:
        """Generate only campaign details from every already-selected value."""

        raw = self.client.generate_campaign_details(context=self._draft_context(draft))
        name = raw.get("campaign_name")
        description = raw.get("campaign_description")
        if not isinstance(name, str) or not isinstance(description, str):
            raise LMStudioResponseError("Generated campaign details were invalid.")
        return replace(
            draft,
            campaign_name=name,
            campaign_description=description,
        )

    def generate_intro(self, draft: CharacterCreationDraft) -> str:
        """Generate a bounded opening scene from the final confirmed profile."""

        return self.client.generate_campaign_introduction(
            context=self._draft_context(draft)
        )

    @staticmethod
    def fallback_intro(draft: CharacterCreationDraft) -> str:
        """Provide a deterministic opening when local generation is unavailable."""

        preset_intro = preset_fallback_intro(draft)
        if preset_intro is not None:
            return preset_intro

        identity = f"{draft.name}, a {draft.ancestry} {draft.character_class}"
        purpose = draft.motivation.rstrip(".") or "an uncertain purpose"
        premise = " ".join(draft.campaign_description.split())
        return (
            f"{draft.starting_location} stirs beneath the atmosphere of "
            f"{draft.tone.lower()}. In this {draft.world_type.lower()} world, {identity} "
            f"arrives in {draft.starting_region} carrying {draft.primary_weapon} and the "
            f"weight of {purpose.lower()}. {premise} Nearby movement, unfamiliar voices, "
            "and the shape of the road ahead offer several immediate choices. The adventure "
            "has begun, and the next decision belongs to you."
        )

    @staticmethod
    def _draft_context(draft: CharacterCreationDraft) -> dict[str, Any]:
        biography_backstory = " ".join(
            value.strip() for value in (draft.biography, draft.backstory) if value.strip()
        )
        context = {
            "campaign": {
                "name": draft.campaign_name,
                "premise": draft.campaign_description,
                "world_type": draft.world_type,
                "tone": draft.tone,
                "starting_region": draft.starting_region,
                "starting_location": draft.starting_location,
                "difficulty": draft.difficulty,
                "content_preferences": (
                    draft.content_preferences.strip() or DEFAULT_CONTENT_PREFERENCES
                ),
                "visual_style": draft.visual_style,
                "camera_style": draft.camera_style,
            },
            "player": {
                "name": draft.name,
                "ancestry": draft.ancestry,
                "age": draft.age,
                "gender_identity": draft.gender_identity,
                "pronouns": draft.pronouns,
                "body_description": draft.body_description,
                "face_description": draft.face_description,
                "clothing_style": draft.clothing_style,
                "background": draft.background,
                "class": draft.character_class,
                "ability_scores": dict(draft.ability_scores),
                "personality_traits": list(draft.personalities),
                "primary_strength": draft.primary_strength,
                "meaningful_flaw": draft.meaningful_flaw,
                "motivation": draft.motivation,
                "biography_backstory": biography_backstory,
                "focus_skills": list(draft.skills),
            },
            "starting_equipment": {
                "primary_weapon": draft.primary_weapon,
                "secondary_weapon": draft.secondary_weapon,
                "ranged_weapon": draft.ranged_weapon,
                "armor": draft.armor,
                "shield": draft.shield,
                "important_tool": draft.important_tool,
                "keepsake": draft.keepsake,
            },
        }
        if draft.preset_id:
            context["preset_campaign"] = preset_intro_context(draft.preset_id)
        return context
