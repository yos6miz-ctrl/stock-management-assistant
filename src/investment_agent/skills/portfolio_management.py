from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from ..formatting import (
    format_money,
    format_percent,
    format_signed_money,
)
from ..interfaces import MarketDataProvider
from ..models import (
    MarketQuote,
    PortfolioPerformance,
    PortfolioSnapshot,
    Position,
    PositionChange,
    PositionPerformance,
    ProviderStatus,
    QuoteStatus,
    RunStatus,
    SkillRunResult,
    normalize_symbol,
    utc_now,
)
from ..storage import JsonStateStore


LOGGER = logging.getLogger(__name__)


class PortfolioTrackerSkill:
    """Skill 1: confirmed holdings plus calculated market performance."""

    name = "portfolio_tracker"

    def __init__(
        self,
        store: JsonStateStore,
        market_data_provider: MarketDataProvider,
        base_currency: str = "USD",
    ):
        self.store = store
        self.market_data_provider = market_data_provider
        self.base_currency = base_currency

    def add_position(
        self,
        symbol: str,
        quantity: str,
        average_purchase_price: str,
        notes: str = "",
    ) -> Position:
        LOGGER.info("Adding confirmed portfolio position %s", symbol.upper())
        return self.store.add_position(
            symbol, quantity, average_purchase_price, notes
        )

    def record_buy(
        self,
        symbol: str,
        quantity: str,
        purchase_price: str,
        notes: str | None = None,
    ) -> Position:
        LOGGER.info("Recording user-confirmed purchase for %s", symbol.upper())
        return self.store.record_buy(symbol, quantity, purchase_price, notes)

    def record_sell(self, symbol: str, quantity: str) -> Position | None:
        LOGGER.info("Recording user-confirmed sale for %s", symbol.upper())
        return self.store.record_sell(symbol, quantity)

    def correct_position(
        self,
        symbol: str,
        *,
        quantity: str | None = None,
        average_purchase_price: str | None = None,
        notes: str | None = None,
    ) -> Position:
        LOGGER.info("Correcting confirmed portfolio position %s", symbol.upper())
        return self.store.correct_position(
            symbol,
            quantity=quantity,
            average_purchase_price=average_purchase_price,
            notes=notes,
        )

    def remove_position(self, symbol: str) -> None:
        LOGGER.info("Removing user-confirmed portfolio position %s", symbol.upper())
        self.store.remove_position(symbol)

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        return self.store.get_portfolio_snapshot()

    def get_latest_performance(self) -> PortfolioPerformance | None:
        return self.store.get_latest_performance()

    def history(self) -> list[dict[str, Any]]:
        return self.store.portfolio_events()

    def run(self) -> SkillRunResult:
        snapshot = self.get_portfolio_snapshot()
        previous = self.get_latest_performance()
        symbols = tuple(position.symbol for position in snapshot.positions)
        market_batch = self.market_data_provider.get_quotes(symbols)
        provided_quotes = self._validated_quotes(market_batch.quotes, symbols)
        previous_positions = {
            item.position.symbol: item
            for item in previous.positions
        } if previous else {}

        prepared: list[
            tuple[Position, MarketQuote | None, str, PositionChange | None]
        ] = []
        for position in snapshot.positions:
            quote = provided_quotes.get(position.symbol)
            note = ""
            if quote is None:
                previous_item = previous_positions.get(position.symbol)
                if previous_item and previous_item.quote:
                    old_quote = previous_item.quote
                    quote = MarketQuote(
                        symbol=position.symbol,
                        price=old_quote.price,
                        as_of=old_quote.as_of,
                        source=old_quote.source,
                        status=QuoteStatus.OUTDATED,
                        currency=old_quote.currency,
                    )
                    note = (
                        "Live price unavailable; using saved price labeled "
                        f"outdated as of {old_quote.as_of}."
                    )
                else:
                    note = market_batch.errors.get(
                        position.symbol,
                        "Current price is unavailable and no saved price exists.",
                    )
            elif quote.currency != self.base_currency:
                note = (
                    f"Quote currency {quote.currency} does not match configured "
                    f"portfolio currency {self.base_currency}."
                )
                quote = None
            else:
                note = f"Market price from {quote.source} as of {quote.as_of}."

            change = self._calculate_change(
                position,
                quote,
                previous_positions.get(position.symbol),
            )
            prepared.append((position, quote, note, change))

        quoted_values = [
            position.quantity * quote.price
            for position, quote, _, _ in prepared
            if quote is not None
        ]
        has_all_values = len(quoted_values) == len(prepared)
        total_current = (
            sum(quoted_values, Decimal("0")) if has_all_values else None
        )
        total_invested = snapshot.total_invested

        performances = []
        for position, quote, note, change in prepared:
            current_value = (
                position.quantity * quote.price if quote is not None else None
            )
            profit_loss = (
                current_value - position.invested_amount
                if current_value is not None
                else None
            )
            return_percent = (
                profit_loss / position.invested_amount * Decimal("100")
                if profit_loss is not None and position.invested_amount != 0
                else None
            )
            weight = (
                current_value / total_current * Decimal("100")
                if current_value is not None
                and total_current is not None
                and total_current != 0
                else None
            )
            performances.append(
                PositionPerformance(
                    position=position,
                    quote=quote,
                    invested_amount=position.invested_amount,
                    current_value=current_value,
                    profit_loss=profit_loss,
                    return_percent=return_percent,
                    portfolio_weight_percent=weight,
                    change_since_previous=change,
                    market_data_note=note,
                )
            )

        total_profit = (
            total_current - total_invested
            if total_current is not None
            else None
        )
        total_return = (
            total_profit / total_invested * Decimal("100")
            if total_profit is not None and total_invested != 0
            else Decimal("0") if total_invested == 0 else None
        )
        complete_market_data = (
            market_batch.status == ProviderStatus.AVAILABLE
            and all(
                item.quote is not None
                and item.quote.status in {QuoteStatus.LIVE, QuoteStatus.DELAYED}
                for item in performances
            )
        )
        if not performances:
            complete_market_data = True
        if not performances:
            message = "Portfolio is empty; no market prices were required."
        elif complete_market_data:
            message = "Portfolio calculated using current configured market data."
        elif any(item.quote is not None for item in performances):
            message = (
                "Portfolio includes outdated or incomplete market data; "
                "see each position label."
            )
        else:
            message = (
                "Live market data is unavailable and no saved prices can be used."
            )

        performance = PortfolioPerformance(
            portfolio_revision=snapshot.revision,
            calculated_at=utc_now(),
            currency=self.base_currency,
            total_invested=total_invested,
            current_value=total_current,
            profit_loss=total_profit,
            return_percent=total_return,
            complete_market_data=complete_market_data,
            positions=tuple(performances),
            message=message,
        )
        self.store.record_performance(performance)
        if complete_market_data:
            status = RunStatus.COMPLETE
        elif any(item.quote is not None for item in performances):
            status = RunStatus.PARTIAL
        else:
            status = RunStatus.UNAVAILABLE
        result = SkillRunResult(
            skill=self.name,
            status=status,
            portfolio_revision=snapshot.revision,
            output={"performance": performance.to_dict()},
            message=message,
            created_at=performance.calculated_at,
        )
        self.store.record_skill_run(result.to_dict())
        return result

    def format_result(self, result: SkillRunResult) -> str:
        performance = PortfolioPerformance.from_dict(
            result.output["performance"]
        )
        lines = [
            f"Portfolio value: {format_money(performance.current_value)}",
            f"Invested (confirmed): {format_money(performance.total_invested)}",
            (
                "Total return: "
                f"{format_signed_money(performance.profit_loss)} "
                f"({format_percent(performance.return_percent, signed=True)})"
            ),
            f"Market data: {performance.message}",
        ]
        for item in performance.positions:
            if item.quote is None:
                lines.append(
                    f"* {item.position.symbol}: price unavailable | "
                    f"Invested: {format_money(item.invested_amount)}"
                )
                continue
            status_label = (
                f" ({item.quote.status.value}, {item.quote.as_of})"
                if item.quote.status != QuoteStatus.LIVE
                else ""
            )
            line = (
                f"* {item.position.symbol}: "
                f"{format_money(item.quote.price)}{status_label} | "
                f"{format_percent(item.return_percent, signed=True)} | "
                f"Position value: {format_money(item.current_value)} | "
                f"Weight: {format_percent(item.portfolio_weight_percent)}"
            )
            if item.change_since_previous:
                line += (
                    " | Since previous: "
                    f"{format_percent(item.change_since_previous.price_change_percent, signed=True)}"
                )
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _validated_quotes(
        quotes: tuple[MarketQuote, ...],
        requested_symbols: tuple[str, ...],
    ) -> dict[str, MarketQuote]:
        requested = set(requested_symbols)
        validated: dict[str, MarketQuote] = {}
        for quote in quotes:
            symbol = normalize_symbol(quote.symbol)
            if symbol not in requested:
                raise ValueError(
                    f"market provider returned unrequested symbol {symbol}"
                )
            if symbol in validated:
                raise ValueError(
                    f"market provider returned duplicate quote for {symbol}"
                )
            if quote.price < 0:
                raise ValueError(
                    f"market provider returned a negative price for {symbol}"
                )
            if quote.status == QuoteStatus.UNAVAILABLE:
                raise ValueError(
                    f"market provider returned an unusable quote for {symbol}"
                )
            if not quote.as_of.strip() or not quote.source.strip():
                raise ValueError(
                    f"market provider omitted quote provenance for {symbol}"
                )
            validated[symbol] = quote
        return validated

    @staticmethod
    def _calculate_change(
        position: Position,
        quote: MarketQuote | None,
        previous: PositionPerformance | None,
    ) -> PositionChange | None:
        if quote is None or previous is None or previous.quote is None:
            return None
        price_change = quote.price - previous.quote.price
        percent = (
            price_change / previous.quote.price * Decimal("100")
            if previous.quote.price != 0
            else None
        )
        current_value = position.quantity * quote.price
        previous_value = previous.current_value or Decimal("0")
        return PositionChange(
            previous_as_of=previous.quote.as_of,
            price_change=price_change,
            price_change_percent=percent,
            value_change=current_value - previous_value,
        )
