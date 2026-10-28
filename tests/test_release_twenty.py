from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from dd_simulator.state import GameStateDatabase, GameStateError, GameStateService
from dd_simulator.state.commerce import merchant_price
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.themes.theme_manager import ThemeManager


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def _service() -> GameStateService:
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    assert service.initialize() == 23
    service.ensure_demo_campaign()
    return service


def _merchant(service: GameStateService):  # type: ignore[no-untyped-def]
    dashboard = service.load_active_dashboard()
    conversation = next(
        value for value in dashboard.npc_conversations
        if value.npc.id == "npc-roadside-merchant"
    )
    assert conversation.merchant is not None
    return conversation.merchant


def test_buy_barter_and_sell_are_atomic_persistent_transactions() -> None:
    service = _service()
    merchant = _merchant(service)
    potion = next(item for item in merchant.stock if item.name == "Health Potion")
    before_currency = merchant.player_currency
    before_quantity = potion.quantity

    bought = service.complete_trade(merchant.npc_id, "buy", potion.id)
    after_buy = _merchant(service)

    assert bought.remaining_currency == before_currency - potion.buy_price
    assert next(item for item in after_buy.stock if item.id == potion.id).quantity == before_quantity - 1

    rope = next(item for item in after_buy.stock if item.name == "Rope")
    bartered = service.complete_trade(after_buy.npc_id, "barter", rope.id)
    assert bartered.quote.total_price == rope.barter_price
    assert rope.barter_price <= rope.buy_price

    sellable = next(item for item in _merchant(service).sellable_items if item.name == "Lockpick")
    sold = service.complete_trade(merchant.npc_id, "sell", sellable.id)
    assert sold.remaining_currency == bartered.remaining_currency + sellable.sell_price

    with service.database.connect() as connection:
        actions = tuple(
            row[0] for row in connection.execute(
                "SELECT action FROM commerce_transactions ORDER BY created_at, rowid"
            )
        )
        summaries = tuple(
            row[0] for row in connection.execute(
                "SELECT summary FROM events WHERE summary LIKE '%gold.' ORDER BY sequence"
            )
        )
    assert actions == ("buy", "barter", "sell")
    assert len(summaries) == 3


def test_failed_purchase_does_not_change_stock_or_currency() -> None:
    service = _service()
    merchant = _merchant(service)
    item = merchant.stock[0]
    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE characters SET currency = 0 WHERE campaign_id = ? AND is_player = 1",
            (service.campaigns.active_campaign_id(),),
        )

    with pytest.raises(GameStateError, match="enough gold"):
        service.complete_trade(merchant.npc_id, "buy", item.id)

    refreshed = _merchant(service)
    assert refreshed.player_currency == 0
    assert next(value for value in refreshed.stock if value.id == item.id).quantity == item.quantity


def test_pricing_uses_rarity_condition_difficulty_relationship_and_barter() -> None:
    ordinary = merchant_price(10, "common", 100, 100, "Adventurer", 0, action="buy")
    rare = merchant_price(10, "rare", 100, 100, "Adventurer", 0, action="buy")
    damaged = merchant_price(10, "common", 20, 100, "Adventurer", 0, action="buy")
    friendly = merchant_price(10, "common", 100, 100, "Adventurer", 40, action="buy")
    bartered = merchant_price(10, "common", 100, 100, "Adventurer", 40, action="barter")

    assert rare > ordinary > damaged
    assert friendly < ordinary
    assert bartered < friendly


def test_people_trade_ui_and_centered_footers(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    service = _service()
    themes = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    ).available_themes()
    window = MainWindow(themes, service.load_active_dashboard(), game_state_service=service)
    window.resize(1600, 900)
    window.controller.navigate("people")
    window.show()
    app.processEvents()

    assert window.findChild(QWidget, "merchantTradePanel") is not None
    assert len(window.findChildren(QWidget, "merchantBuyButton")) == 6
    assert len(window.findChildren(QWidget, "npcSuggestedResponse")) == 6
    footer = window.findChild(QWidget, "npcCenteredFooter")
    controls = window.findChild(QWidget, "npcBottomControls")
    assert footer is not None and controls is not None
    assert abs(controls.width() * 3 - footer.width()) < 40

    for target in ("map",):
        window.controller.navigate(target)
        app.processEvents()
        page = window.navigation_pages[target]
        back = page.findChild(QWidget, "navigationBackButton")
        assert back is not None
        assert back.width() < page.width() // 2

    window.controller.navigate("settings")
    app.processEvents()
    settings_back = window.findChild(QWidget, "settingsBackButton")
    assert settings_back is not None
    assert settings_back.width() < window.settings_page.width() // 2
    window.close()
