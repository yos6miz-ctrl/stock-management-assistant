from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..models import Position
from ..store import StateStore


class PortfolioManagement:
    """Skill 1: the sole writer of portfolio holdings."""

    def __init__(self, store: StateStore):
        self.store = store

    def add(
        self,
        symbol: str,
        quantity: str | int | float | Decimal,
        average_price: str | int | float | Decimal,
        notes: str = "",
    ) -> Position:
        return self.store.add_position(symbol, quantity, average_price, notes)

    def update(
        self,
        symbol: str,
        *,
        quantity: str | int | float | Decimal | None = None,
        average_price: str | int | float | Decimal | None = None,
        notes: str | None = None,
    ) -> Position:
        return self.store.update_position(
            symbol,
            quantity=quantity,
            average_price=average_price,
            notes=notes,
        )

    def remove(self, symbol: str) -> None:
        self.store.remove_position(symbol)

    def current(self) -> dict[str, Any]:
        return self.store.portfolio_snapshot().as_dict()

    def history(self) -> list[dict[str, Any]]:
        return self.store.portfolio_history()
