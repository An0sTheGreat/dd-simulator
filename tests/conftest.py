from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _close_leftover_widgets():  # type: ignore[no-untyped-def]
    """Destroy every top-level widget a test leaves behind.

    The QApplication is shared by the whole run. Without this, each test's windows stay
    alive and every later ``setStyleSheet`` re-polishes all of them, so a two-second
    bootstrap test grows to over thirty seconds late in the suite.
    """

    yield
    app = QApplication.instance()
    if app is None:
        return
    # Panels queue zero-delay QTimer callbacks without a context object; let them run
    # now, while their widgets still exist, instead of in the next test.
    app.processEvents()
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
