"""Small semantic frame used by theme-aware layout regions."""

from PySide6.QtWidgets import QFrame


class ThemedFrame(QFrame):
    """A frame styled only through semantic names and properties."""

    def __init__(self, object_name: str, *, role: str) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setProperty("role", role)
        self.setFrameShape(QFrame.Shape.NoFrame)

