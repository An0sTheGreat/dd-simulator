"""User-safe local model integration failures."""


class LocalModelError(RuntimeError):
    """Base class for local model failures."""


class LocalModelConnectionError(LocalModelError):
    """The local server could not be reached in time."""


class LocalModelAuthenticationError(LocalModelError):
    """The local server rejected the configured API key (HTTP 401)."""


class LocalModelModelError(LocalModelError):
    """No usable loaded model was available."""


class LocalModelResponseError(LocalModelError):
    """The local model returned malformed or unsafe output."""
