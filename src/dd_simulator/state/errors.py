"""Typed failures raised by the Game-State Ledger boundary."""


class GameStateError(RuntimeError):
    """Base exception for safe persistence failures."""


class IncompleteGameStateError(GameStateError):
    """Raised when a campaign cannot yet produce a dashboard projection."""


class ItemActionError(GameStateError):
    """Raised when a deterministic inventory command is invalid."""


class CombatError(GameStateError):
    """Raised when a deterministic combat command is invalid."""


class ActionResolutionError(GameStateError):
    """Raised when a player action cannot safely produce a committed turn."""


class ActionValidationError(ActionResolutionError):
    """Raised when a proposed state command violates deterministic rules."""


class ActionCancelledError(ActionResolutionError):
    """Raised when the user cancels before the turn transaction begins."""
