"""User-safe LM Studio integration failures."""


class LocalModelError(RuntimeError):
    """Base class for local model failures."""


class LocalModelConnectionError(LocalModelError):
    """The local server could not be reached in time."""


class LocalModelModelError(LocalModelError):
    """No usable loaded model was available."""


class LocalModelResponseError(LocalModelError):
    """The local model returned malformed or unsafe output."""
