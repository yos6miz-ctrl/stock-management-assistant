from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..models import (
    PortfolioPerformance,
    PortfolioSnapshot,
    Position,
    decimal_text,
    decimal_value,
    normalize_symbol,
    utc_now,
)


class StateStorageError(RuntimeError):
    """Raised when persistent JSON state cannot be safely loaded."""


class JsonStateStore:
    """Single-process JSON persistence with atomic file replacement."""

    SCHEMA_VERSION = 3

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write(self._empty_state())
        else:
            state = self._read_unvalidated()
            migrated = self._migrate(state)
            self._validate(migrated)
            if migrated != state:
                self._write(migrated)

    @classmethod
    def _empty_state(cls) -> dict[str, Any]:
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "portfolio": {"revision": 0, "positions": [], "events": []},
            "performance_history": [],
            "portfolio_analysis_history": [],
            "opportunity_scan_history": [],
            "reported_events": [],
            "skill_runs": [],
            "last_valid_run": None,
            "notification_history": [],
        }

    def _read_unvalidated(self) -> dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as state_file:
                state: Any = json.load(state_file)
        except (json.JSONDecodeError, OSError) as exc:
            raise StateStorageError(
                f"unable to load JSON state from {self.path}"
            ) from exc
        if not isinstance(state, dict):
            raise StateStorageError("state root must be a JSON object")
        return state

    def _read(self) -> dict[str, Any]:
        with self._lock:
            state = self._migrate(self._read_unvalidated())
            self._validate(state)
            return state

    def _migrate(self, state: dict[str, Any]) -> dict[str, Any]:
        version = state.get("schema_version")
        if version == self.SCHEMA_VERSION:
            return state
        if version not in {1, 2}:
            raise StateStorageError("unsupported state schema version")

        migrated = deepcopy(state)
        migrated["schema_version"] = self.SCHEMA_VERSION
        migrated.setdefault("performance_history", [])
        migrated.setdefault("portfolio_analysis_history", [])
        migrated.setdefault("opportunity_scan_history", [])
        migrated.setdefault("reported_events", [])
        migrated.setdefault("skill_runs", [])
        migrated.setdefault("last_valid_run", None)
        migrated.setdefault("notification_history", [])
        migrated.pop("research_state", None)
        return migrated

    def _validate(self, state: dict[str, Any]) -> None:
        if state.get("schema_version") != self.SCHEMA_VERSION:
            raise StateStorageError("unsupported state schema version")
        portfolio = state.get("portfolio")
        if not isinstance(portfolio, dict):
            raise StateStorageError("state portfolio section is invalid")
        for field in ("positions", "events"):
            if not isinstance(portfolio.get(field), list):
                raise StateStorageError(f"portfolio {field} must be an array")
        if not isinstance(portfolio.get("revision"), int):
            raise StateStorageError("portfolio revision must be an integer")
        for field in (
            "performance_history",
            "portfolio_analysis_history",
            "opportunity_scan_history",
            "reported_events",
            "skill_runs",
            "notification_history",
        ):
            if not isinstance(state.get(field), list):
                raise StateStorageError(f"state {field} must be an array")
        if state.get("last_valid_run") is not None and not isinstance(
            state.get("last_valid_run"), dict
        ):
            raise StateStorageError("last_valid_run must be an object or null")

    def _write(self, state: dict[str, Any]) -> None:
        with self._lock:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                text=True,
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
                    json.dump(state, state_file, indent=2, sort_keys=True)
                    state_file.write("\n")
                    state_file.flush()
                    os.fsync(state_file.fileno())
                os.replace(temporary_path, self.path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

    def state_snapshot(self) -> dict[str, Any]:
        return deepcopy(self._read())

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        state = self._read()
        portfolio = state["portfolio"]
        return PortfolioSnapshot(
            revision=portfolio["revision"],
            positions=tuple(
                Position.from_dict(item) for item in portfolio["positions"]
            ),
            generated_at=utc_now(),
        )

    def add_position(
        self,
        symbol: str,
        quantity: str | int | float | Decimal,
        average_purchase_price: str | int | float | Decimal,
        notes: str = "",
    ) -> Position:
        normalized = normalize_symbol(symbol)
        parsed_quantity = decimal_value(quantity, "quantity")
        parsed_average = decimal_value(
            average_purchase_price, "average_purchase_price"
        )

        with self._lock:
            state = self._read()
            portfolio = state["portfolio"]
            if self._find_position_index(portfolio, normalized) is not None:
                raise ValueError(f"position {normalized} already exists")
            now = utc_now()
            position = Position(
                symbol=normalized,
                quantity=parsed_quantity,
                average_purchase_price=parsed_average,
                notes=notes,
                created_at=now,
                updated_at=now,
            )
            portfolio["positions"].append(position.to_dict())
            portfolio["positions"].sort(key=lambda item: item["symbol"])
            self._append_portfolio_event(
                portfolio,
                action="add",
                symbol=normalized,
                before=None,
                after=position.to_dict(),
                transaction={
                    "quantity": decimal_text(parsed_quantity),
                    "price": decimal_text(parsed_average),
                },
            )
            self._write(state)
            return position

    def record_buy(
        self,
        symbol: str,
        quantity: str | int | float | Decimal,
        purchase_price: str | int | float | Decimal,
        notes: str | None = None,
    ) -> Position:
        normalized = normalize_symbol(symbol)
        bought_quantity = decimal_value(quantity, "quantity")
        price = decimal_value(purchase_price, "purchase_price")

        with self._lock:
            state = self._read()
            portfolio = state["portfolio"]
            index = self._find_position_index(portfolio, normalized)
            now = utc_now()
            if index is None:
                before = None
                updated = Position(
                    symbol=normalized,
                    quantity=bought_quantity,
                    average_purchase_price=price,
                    notes=notes or "",
                    created_at=now,
                    updated_at=now,
                )
                portfolio["positions"].append(updated.to_dict())
                portfolio["positions"].sort(key=lambda item: item["symbol"])
            else:
                current = Position.from_dict(portfolio["positions"][index])
                before = current.to_dict()
                new_quantity = current.quantity + bought_quantity
                new_invested = (
                    current.invested_amount + bought_quantity * price
                )
                updated = Position(
                    symbol=normalized,
                    quantity=new_quantity,
                    average_purchase_price=new_invested / new_quantity,
                    notes=notes if notes is not None else current.notes,
                    created_at=current.created_at,
                    updated_at=now,
                )
                portfolio["positions"][index] = updated.to_dict()

            self._append_portfolio_event(
                portfolio,
                action="buy",
                symbol=normalized,
                before=before,
                after=updated.to_dict(),
                transaction={
                    "quantity": decimal_text(bought_quantity),
                    "price": decimal_text(price),
                },
            )
            self._write(state)
            return updated

    def record_sell(
        self,
        symbol: str,
        quantity: str | int | float | Decimal,
    ) -> Position | None:
        normalized = normalize_symbol(symbol)
        sold_quantity = decimal_value(quantity, "quantity")

        with self._lock:
            state = self._read()
            portfolio = state["portfolio"]
            index = self._find_position_index(portfolio, normalized)
            if index is None:
                raise KeyError(f"position {normalized} was not found")
            current = Position.from_dict(portfolio["positions"][index])
            if sold_quantity > current.quantity:
                raise ValueError(
                    f"cannot sell {sold_quantity}; only {current.quantity} held"
                )

            before = current.to_dict()
            now = utc_now()
            if sold_quantity == current.quantity:
                portfolio["positions"].pop(index)
                updated = None
            else:
                updated = Position(
                    symbol=normalized,
                    quantity=current.quantity - sold_quantity,
                    average_purchase_price=current.average_purchase_price,
                    notes=current.notes,
                    created_at=current.created_at,
                    updated_at=now,
                )
                portfolio["positions"][index] = updated.to_dict()

            self._append_portfolio_event(
                portfolio,
                action="sell",
                symbol=normalized,
                before=before,
                after=updated.to_dict() if updated else None,
                transaction={"quantity": decimal_text(sold_quantity)},
            )
            self._write(state)
            return updated

    def correct_position(
        self,
        symbol: str,
        *,
        quantity: str | int | float | Decimal | None = None,
        average_purchase_price: str | int | float | Decimal | None = None,
        notes: str | None = None,
    ) -> Position:
        normalized = normalize_symbol(symbol)
        if quantity is None and average_purchase_price is None and notes is None:
            raise ValueError("at least one portfolio field must be corrected")

        with self._lock:
            state = self._read()
            portfolio = state["portfolio"]
            index = self._find_position_index(portfolio, normalized)
            if index is None:
                raise KeyError(f"position {normalized} was not found")
            current = Position.from_dict(portfolio["positions"][index])
            updated = Position(
                symbol=normalized,
                quantity=(
                    decimal_value(quantity, "quantity")
                    if quantity is not None
                    else current.quantity
                ),
                average_purchase_price=(
                    decimal_value(
                        average_purchase_price, "average_purchase_price"
                    )
                    if average_purchase_price is not None
                    else current.average_purchase_price
                ),
                notes=notes if notes is not None else current.notes,
                created_at=current.created_at,
                updated_at=utc_now(),
            )
            portfolio["positions"][index] = updated.to_dict()
            self._append_portfolio_event(
                portfolio,
                action="correct",
                symbol=normalized,
                before=current.to_dict(),
                after=updated.to_dict(),
                transaction=None,
            )
            self._write(state)
            return updated

    def remove_position(self, symbol: str) -> None:
        normalized = normalize_symbol(symbol)
        with self._lock:
            state = self._read()
            portfolio = state["portfolio"]
            index = self._find_position_index(portfolio, normalized)
            if index is None:
                raise KeyError(f"position {normalized} was not found")
            removed = portfolio["positions"].pop(index)
            self._append_portfolio_event(
                portfolio,
                action="remove",
                symbol=normalized,
                before=removed,
                after=None,
                transaction=None,
            )
            self._write(state)

    def portfolio_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._read()["portfolio"]["events"])

    def record_performance(self, performance: PortfolioPerformance) -> None:
        with self._lock:
            state = self._read()
            state["performance_history"].append(performance.to_dict())
            self._write(state)

    def get_latest_performance(self) -> PortfolioPerformance | None:
        history = self._read()["performance_history"]
        if not history:
            return None
        return PortfolioPerformance.from_dict(history[-1])

    def previous_recommendations(self) -> dict[str, dict]:
        history = self._read()["portfolio_analysis_history"]
        if not history:
            return {}
        recommendations = history[-1].get("recommendations", [])
        return {
            str(item["symbol"]): deepcopy(item)
            for item in recommendations
            if isinstance(item, dict) and item.get("symbol")
        }

    def record_portfolio_analysis(self, result: dict[str, Any]) -> None:
        with self._lock:
            state = self._read()
            state["portfolio_analysis_history"].append(deepcopy(result))
            self._write(state)

    def record_opportunity_scan(self, result: dict[str, Any]) -> None:
        with self._lock:
            state = self._read()
            state["opportunity_scan_history"].append(deepcopy(result))
            self._write(state)

    def record_skill_run(self, result: dict[str, Any]) -> None:
        with self._lock:
            state = self._read()
            state["skill_runs"].append(deepcopy(result))
            self._write(state)

    def get_last_valid_run(self) -> dict[str, Any] | None:
        value = self._read()["last_valid_run"]
        return deepcopy(value) if value is not None else None

    def notification_fingerprints(self) -> frozenset[str]:
        history = self._read()["notification_history"]
        return frozenset(
            str(item["fingerprint"])
            for item in history
            if isinstance(item, dict) and item.get("fingerprint")
        )

    def commit_valid_run(
        self,
        valid_run: dict[str, Any],
        *,
        notification: dict[str, Any] | None = None,
    ) -> None:
        """Atomically replace the comparison baseline after a valid run."""
        with self._lock:
            state = self._read()
            state["last_valid_run"] = deepcopy(valid_run)
            if notification is not None:
                state["notification_history"].append(deepcopy(notification))
            self._write(state)

    @staticmethod
    def _find_position_index(
        portfolio: dict[str, Any], symbol: str
    ) -> int | None:
        for index, item in enumerate(portfolio["positions"]):
            if item["symbol"] == symbol:
                return index
        return None

    @staticmethod
    def _append_portfolio_event(
        portfolio: dict[str, Any],
        *,
        action: str,
        symbol: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        transaction: dict[str, Any] | None,
    ) -> None:
        portfolio["revision"] += 1
        portfolio["events"].append(
            {
                "revision": portfolio["revision"],
                "action": action,
                "symbol": symbol,
                "before": before,
                "after": after,
                "transaction": transaction,
                "created_at": utc_now(),
            }
        )
