"""Typed non-combat turn outcomes shared by the LLM and ledger boundary."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ProposedStateChange:
    operation: str
    target_type: str
    target_id: str
    field: str | None
    value: Any
    reason: str


@dataclass(frozen=True, slots=True)
class NarrativeSegment:
    kind: str
    text: str
    speaker_id: str | None = None


@dataclass(frozen=True, slots=True)
class SkillCheckResult:
    name: str
    roll: int
    modifier: int
    total: int
    target: int
    success: bool


def sanitize_model_text(value: str) -> str:
    """Return plain display text without model-added markup wrappers."""

    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^\s*```[^\n]*\n?", "", text).replace("```", "")
    text = re.sub(r"!?\[([^\]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"</?[A-Za-z][^>\n]{0,79}>", "", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*(?:[-+â€¢]|\d+[.)])\s+", "", text)
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"(?<!\w)_{1,2}(?=\S)|(?<=\S)_{1,2}(?!\w)", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(lines).strip()


def limit_words(text: str, maximum: int) -> str:
    """Normalize whitespace and cap model-authored prose at a word boundary."""

    if maximum <= 0:
        return ""
    words = text.split()
    if len(words) <= maximum:
        return " ".join(words)
    return " ".join(words[:maximum]).rstrip(".,;:!?—-") + "…"


def limit_narrative_segments(
    segments: tuple[NarrativeSegment, ...] | list[NarrativeSegment],
    maximum: int = 125,
) -> tuple[NarrativeSegment, ...]:
    remaining = maximum
    bounded: list[NarrativeSegment] = []
    for segment in segments:
        if remaining <= 0:
            break
        text = limit_words(segment.text, remaining)
        bounded.append(NarrativeSegment(segment.kind, text, segment.speaker_id))
        remaining -= len(text.split())
    return tuple(bounded)


def normalize_narrative_segment(
    kind: str,
    text: str,
    speaker_id: str | None = None,
) -> tuple[NarrativeSegment, ...]:
    """Preserve model-authored prose while removing transport wrappers."""

    return (NarrativeSegment(kind, sanitize_model_text(text), speaker_id),)


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    narration: str
    state_changes: tuple[ProposedStateChange, ...]
    quest_notes: tuple[str, ...]
    suggested_actions: tuple[str, ...]
    narrative_segments: tuple[NarrativeSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionResolutionResult:
    turn_id: str
    narration: str
    state_summaries: tuple[str, ...]


class ActionOutcomeProvider(Protocol):
    def resolve_action(
        self,
        *,
        action: str,
        context: dict[str, Any],
    ) -> ActionOutcome: ...


_PENDING_NOTES_TABLE = (
    "CREATE TEMP TABLE IF NOT EXISTS pending_turn_notes("
    "campaign_id TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL)"
)


def record_turn_note(
    connection: sqlite3.Connection, campaign_id: str, kind: str, text: str
) -> None:
    """Buffer a short player-facing note for the turn this transaction writes.

    The buffer is a connection-scoped TEMP table, and each transaction uses its own
    connection, so notes from flows that write no transcript message (panel actions,
    trading, crafting) are discarded with the connection instead of leaking into a
    later turn.
    """

    connection.execute(_PENDING_NOTES_TABLE)
    connection.execute(
        "INSERT INTO temp.pending_turn_notes(campaign_id, kind, text) VALUES (?, ?, ?)",
        (campaign_id, kind, text[:120]),
    )


def claim_turn_notes(
    connection: sqlite3.Connection, campaign_id: str, turn_number: int
) -> None:
    """Attach this transaction's buffered notes to the turn whose messages it wrote."""

    connection.execute(_PENDING_NOTES_TABLE)
    connection.execute(
        "INSERT INTO turn_notes(campaign_id, turn_number, kind, text) "
        "SELECT campaign_id, ?, kind, text FROM temp.pending_turn_notes "
        "WHERE campaign_id = ? ORDER BY rowid",
        (turn_number, campaign_id),
    )
    connection.execute(
        "DELETE FROM temp.pending_turn_notes WHERE campaign_id = ?", (campaign_id,)
    )
