"""User-safe LM Studio integration failures."""


class LMStudioError(RuntimeError):
    """Base class for local model failures."""


class LMStudioConnectionError(LMStudioError):
    """The local server could not be reached in time."""


class LMStudioModelError(LMStudioError):
    """No usable loaded model was available."""


class LMStudioResponseError(LMStudioError):
    """The local model returned malformed or unsafe output."""
