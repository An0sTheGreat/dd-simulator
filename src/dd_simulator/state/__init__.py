"""SQLite-backed authoritative game-state infrastructure."""

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.commerce import CommerceQuote, CommerceResult
from dd_simulator.state.crafting import CraftingResult
from dd_simulator.state.combat import (
    CombatAction,
    CombatActionResult,
    CombatCommand,
    CombatNarrationOutcome,
    EnemySpec,
)
from dd_simulator.state.errors import (
    ActionCancelledError,
    ActionResolutionError,
    ActionValidationError,
    CombatError,
    GameStateError,
    IncompleteGameStateError,
    ItemActionError,
)
from dd_simulator.state.item_actions import ItemAction, ItemCommand, ItemMutationResult
from dd_simulator.state.reliability import (
    CampaignCheckpoint,
    ReliabilityService,
    RepairIssue,
    RepairResult,
    ReplayResult,
)
from dd_simulator.state.service import GameStateService
from dd_simulator.state.turns import (
    ActionOutcome,
    ActionResolutionResult,
    NarrativeSegment,
    ProposedStateChange,
    SkillCheckResult,
)
from dd_simulator.state.travel import CampResult, TravelResult
from dd_simulator.state.visuals import (
    VisualAssetRecord,
    VisualHistoryRecord,
    VisualRegistryService,
)

__all__ = [
    "GameStateDatabase",
    "ActionCancelledError",
    "ActionOutcome",
    "ActionResolutionError",
    "ActionResolutionResult",
    "ActionValidationError",
    "CombatAction",
    "CombatActionResult",
    "CombatCommand",
    "CombatError",
    "CombatNarrationOutcome",
    "CommerceQuote",
    "CommerceResult",
    "CraftingResult",
    "EnemySpec",
    "GameStateError",
    "GameStateService",
    "IncompleteGameStateError",
    "ItemAction",
    "ItemActionError",
    "ItemCommand",
    "ItemMutationResult",
    "NarrativeSegment",
    "ProposedStateChange",
    "SkillCheckResult",
    "CampResult",
    "CampaignCheckpoint",
    "ReliabilityService",
    "RepairIssue",
    "RepairResult",
    "ReplayResult",
    "TravelResult",
    "VisualAssetRecord",
    "VisualHistoryRecord",
    "VisualRegistryService",
]
