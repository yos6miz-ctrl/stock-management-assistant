from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class ValidationError(ValueError):
    """Raised when user, provider, or persisted data is invalid."""


class RunStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ProviderStatus(StrEnum):
    AVAILABLE = "available"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


class QuoteStatus(StrEnum):
    LIVE = "live"
    DELAYED = "delayed"
    OUTDATED = "outdated"
    UNAVAILABLE = "unavailable"


class RecommendationAction(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    BUY_MORE = "buy_more"
    HOLD = "hold"
    REDUCE = "reduce"
    SELL = "sell"


class OpportunityRating(StrEnum):
    AGGRESSIVE_BUY = "aggressive_buy"
    WATCH = "watch"
    AVOID = "avoid"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOT_AVAILABLE = "not_available"


class CatalystStatus(StrEnum):
    CONFIRMED = "confirmed"
    EXPECTED = "expected"
    ESTIMATED = "estimated"
    RUMORED = "rumored"
    UNKNOWN = "unknown"


class EvidenceKind(StrEnum):
    FACT = "fact"
    MANAGEMENT_CLAIM = "management_claim"
    ESTIMATE = "estimate"
    RUMOR = "rumor"
    CONCLUSION = "conclusion"


class SourceAuthority(StrEnum):
    PRIMARY = "primary"
    AUTHORITATIVE = "authoritative"
    SECONDARY = "secondary"
    ALTERNATIVE = "alternative"


class OpportunityRiskClass(StrEnum):
    LOWER_RISK_AGGRESSIVE = "lower_risk_aggressive"
    HIGH_RISK = "high_risk"
    BINARY_SPECULATIVE = "binary_speculative"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not symbol or len(symbol) > 32:
        raise ValidationError("symbol must contain between 1 and 32 characters")
    if any(character.isspace() for character in symbol):
        raise ValidationError("symbol cannot contain whitespace")
    return symbol


def decimal_value(
    value: str | int | float | Decimal,
    field: str,
    *,
    allow_zero: bool = False,
) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(f"{field} must be a decimal number") from exc
    minimum_valid = parsed >= 0 if allow_zero else parsed > 0
    if not parsed.is_finite() or not minimum_valid:
        qualifier = "zero or greater" if allow_zero else "greater than zero"
        raise ValidationError(f"{field} must be {qualifier}")
    return parsed


def decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: Decimal
    average_purchase_price: Decimal
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def invested_amount(self) -> Decimal:
        return self.quantity * self.average_purchase_price

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": decimal_text(self.quantity),
            "average_purchase_price": decimal_text(self.average_purchase_price),
            "invested_amount": decimal_text(self.invested_amount),
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Position":
        return cls(
            symbol=normalize_symbol(str(value["symbol"])),
            quantity=decimal_value(value["quantity"], "quantity"),
            average_purchase_price=decimal_value(
                value["average_purchase_price"], "average_purchase_price"
            ),
            notes=str(value.get("notes", "")),
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


@dataclass(frozen=True)
class PortfolioSnapshot:
    revision: int
    positions: tuple[Position, ...]
    generated_at: str

    @property
    def total_invested(self) -> Decimal:
        return sum(
            (position.invested_amount for position in self.positions),
            Decimal("0"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "generated_at": self.generated_at,
            "position_count": len(self.positions),
            "total_invested": decimal_text(self.total_invested),
            "positions": [position.to_dict() for position in self.positions],
        }


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    price: Decimal
    as_of: str
    source: str
    status: QuoteStatus
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": decimal_text(self.price),
            "as_of": self.as_of,
            "source": self.source,
            "status": self.status.value,
            "currency": self.currency,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MarketQuote":
        return cls(
            symbol=normalize_symbol(str(value["symbol"])),
            price=decimal_value(value["price"], "price", allow_zero=True),
            as_of=str(value["as_of"]),
            source=str(value["source"]),
            status=QuoteStatus(str(value["status"])),
            currency=str(value.get("currency", "USD")),
        )


@dataclass(frozen=True)
class MarketDataBatch:
    status: ProviderStatus
    quotes: tuple[MarketQuote, ...]
    errors: dict[str, str]
    requested_at: str
    message: str


@dataclass(frozen=True)
class PositionChange:
    previous_as_of: str
    price_change: Decimal
    price_change_percent: Decimal | None
    value_change: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_as_of": self.previous_as_of,
            "price_change": decimal_text(self.price_change),
            "price_change_percent": decimal_text(self.price_change_percent),
            "value_change": decimal_text(self.value_change),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PositionChange":
        raw_percent = value.get("price_change_percent")
        return cls(
            previous_as_of=str(value["previous_as_of"]),
            price_change=Decimal(str(value["price_change"])),
            price_change_percent=(
                Decimal(str(raw_percent)) if raw_percent is not None else None
            ),
            value_change=Decimal(str(value["value_change"])),
        )


@dataclass(frozen=True)
class PositionPerformance:
    position: Position
    quote: MarketQuote | None
    invested_amount: Decimal
    current_value: Decimal | None
    profit_loss: Decimal | None
    return_percent: Decimal | None
    portfolio_weight_percent: Decimal | None
    change_since_previous: PositionChange | None
    market_data_note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position.to_dict(),
            "quote": self.quote.to_dict() if self.quote else None,
            "invested_amount": decimal_text(self.invested_amount),
            "current_value": decimal_text(self.current_value),
            "profit_loss": decimal_text(self.profit_loss),
            "return_percent": decimal_text(self.return_percent),
            "portfolio_weight_percent": decimal_text(
                self.portfolio_weight_percent
            ),
            "change_since_previous": (
                self.change_since_previous.to_dict()
                if self.change_since_previous
                else None
            ),
            "market_data_note": self.market_data_note,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PositionPerformance":
        def optional_decimal(field: str) -> Decimal | None:
            raw = value.get(field)
            return Decimal(str(raw)) if raw is not None else None

        return cls(
            position=Position.from_dict(value["position"]),
            quote=(
                MarketQuote.from_dict(value["quote"])
                if value.get("quote") is not None
                else None
            ),
            invested_amount=Decimal(str(value["invested_amount"])),
            current_value=optional_decimal("current_value"),
            profit_loss=optional_decimal("profit_loss"),
            return_percent=optional_decimal("return_percent"),
            portfolio_weight_percent=optional_decimal(
                "portfolio_weight_percent"
            ),
            change_since_previous=(
                PositionChange.from_dict(value["change_since_previous"])
                if value.get("change_since_previous")
                else None
            ),
            market_data_note=str(value.get("market_data_note", "")),
        )


@dataclass(frozen=True)
class PortfolioPerformance:
    portfolio_revision: int
    calculated_at: str
    currency: str
    total_invested: Decimal
    current_value: Decimal | None
    profit_loss: Decimal | None
    return_percent: Decimal | None
    complete_market_data: bool
    positions: tuple[PositionPerformance, ...]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_revision": self.portfolio_revision,
            "calculated_at": self.calculated_at,
            "currency": self.currency,
            "total_invested": decimal_text(self.total_invested),
            "current_value": decimal_text(self.current_value),
            "profit_loss": decimal_text(self.profit_loss),
            "return_percent": decimal_text(self.return_percent),
            "complete_market_data": self.complete_market_data,
            "positions": [position.to_dict() for position in self.positions],
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PortfolioPerformance":
        def optional_decimal(field: str) -> Decimal | None:
            raw = value.get(field)
            return Decimal(str(raw)) if raw is not None else None

        return cls(
            portfolio_revision=int(value["portfolio_revision"]),
            calculated_at=str(value["calculated_at"]),
            currency=str(value.get("currency", "USD")),
            total_invested=Decimal(str(value["total_invested"])),
            current_value=optional_decimal("current_value"),
            profit_loss=optional_decimal("profit_loss"),
            return_percent=optional_decimal("return_percent"),
            complete_market_data=bool(value["complete_market_data"]),
            positions=tuple(
                PositionPerformance.from_dict(item)
                for item in value.get("positions", [])
            ),
            message=str(value.get("message", "")),
        )


@dataclass(frozen=True)
class SourceReference:
    publisher: str
    url: str
    retrieved_at: str
    authority: SourceAuthority

    def to_dict(self) -> dict[str, Any]:
        return {
            "publisher": self.publisher,
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "authority": self.authority.value,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceReference":
        return cls(
            publisher=str(value["publisher"]),
            url=str(value["url"]),
            retrieved_at=str(value["retrieved_at"]),
            authority=SourceAuthority(str(value["authority"])),
        )


@dataclass(frozen=True)
class EvidenceItem:
    statement: str
    kind: EvidenceKind
    sources: tuple[SourceReference, ...]
    event_time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "kind": self.kind.value,
            "event_time": self.event_time,
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EvidenceItem":
        return cls(
            statement=str(value["statement"]),
            kind=EvidenceKind(str(value["kind"])),
            event_time=(
                str(value["event_time"])
                if value.get("event_time") is not None
                else None
            ),
            sources=tuple(
                SourceReference.from_dict(item)
                for item in value.get("sources", [])
            ),
        )


@dataclass(frozen=True)
class Catalyst:
    event: str
    timing: str
    status: CatalystStatus
    sources: tuple[SourceReference, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "timing": self.timing,
            "status": self.status.value,
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Catalyst":
        return cls(
            event=str(value["event"]),
            timing=str(value["timing"]),
            status=CatalystStatus(str(value["status"])),
            sources=tuple(
                SourceReference.from_dict(item)
                for item in value.get("sources", [])
            ),
        )


@dataclass(frozen=True)
class HoldingRecommendation:
    symbol: str
    action: RecommendationAction
    action_detail: str
    why: str
    future_catalyst: Catalyst
    change_condition: str
    main_risk: str
    confidence: Confidence
    evidence: tuple[EvidenceItem, ...]
    researched_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "action_detail": self.action_detail,
            "why": self.why,
            "future_catalyst": self.future_catalyst.to_dict(),
            "change_condition": self.change_condition,
            "main_risk": self.main_risk,
            "confidence": self.confidence.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "researched_at": self.researched_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "HoldingRecommendation":
        return cls(
            symbol=normalize_symbol(str(value["symbol"])),
            action=RecommendationAction(str(value["action"])),
            action_detail=str(value["action_detail"]),
            why=str(value["why"]),
            future_catalyst=Catalyst.from_dict(value["future_catalyst"]),
            change_condition=str(value["change_condition"]),
            main_risk=str(value["main_risk"]),
            confidence=Confidence(str(value["confidence"])),
            evidence=tuple(
                EvidenceItem.from_dict(item)
                for item in value.get("evidence", [])
            ),
            researched_at=str(value["researched_at"]),
        )


@dataclass(frozen=True)
class PortfolioAnalysisBatch:
    status: ProviderStatus
    recommendations: tuple[HoldingRecommendation, ...]
    researched_at: str
    message: str


@dataclass(frozen=True)
class OpportunityCandidate:
    symbol: str
    rating: OpportunityRating
    catalyst: Catalyst
    why_it_may_move: str
    why_it_may_be_mispriced: str
    entry_condition: str
    target_range: str
    exit_plan: str
    holding_period: str
    maximum_position_percent: Decimal
    risk_class: OpportunityRiskClass
    main_risk: str
    confidence: Confidence
    expected_upside_percent: Decimal
    risk_score: int
    ranking_score: Decimal
    evidence: tuple[EvidenceItem, ...]
    researched_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rating": self.rating.value,
            "catalyst": self.catalyst.to_dict(),
            "why_it_may_move": self.why_it_may_move,
            "why_it_may_be_mispriced": self.why_it_may_be_mispriced,
            "entry_condition": self.entry_condition,
            "target_range": self.target_range,
            "exit_plan": self.exit_plan,
            "holding_period": self.holding_period,
            "maximum_position_percent": decimal_text(
                self.maximum_position_percent
            ),
            "risk_class": self.risk_class.value,
            "main_risk": self.main_risk,
            "confidence": self.confidence.value,
            "expected_upside_percent": decimal_text(
                self.expected_upside_percent
            ),
            "risk_score": self.risk_score,
            "ranking_score": decimal_text(self.ranking_score),
            "evidence": [item.to_dict() for item in self.evidence],
            "researched_at": self.researched_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OpportunityCandidate":
        return cls(
            symbol=normalize_symbol(str(value["symbol"])),
            rating=OpportunityRating(str(value["rating"])),
            catalyst=Catalyst.from_dict(value["catalyst"]),
            why_it_may_move=str(value["why_it_may_move"]),
            why_it_may_be_mispriced=str(value["why_it_may_be_mispriced"]),
            entry_condition=str(value["entry_condition"]),
            target_range=str(value["target_range"]),
            exit_plan=str(value["exit_plan"]),
            holding_period=str(value["holding_period"]),
            maximum_position_percent=Decimal(
                str(value["maximum_position_percent"])
            ),
            risk_class=OpportunityRiskClass(str(value["risk_class"])),
            main_risk=str(value["main_risk"]),
            confidence=Confidence(str(value["confidence"])),
            expected_upside_percent=Decimal(
                str(value["expected_upside_percent"])
            ),
            risk_score=int(value["risk_score"]),
            ranking_score=Decimal(str(value["ranking_score"])),
            evidence=tuple(
                EvidenceItem.from_dict(item)
                for item in value.get("evidence", [])
            ),
            researched_at=str(value["researched_at"]),
        )


@dataclass(frozen=True)
class OpportunityScanBatch:
    status: ProviderStatus
    candidates: tuple[OpportunityCandidate, ...]
    researched_at: str
    message: str


@dataclass(frozen=True)
class SkillRunResult:
    skill: str
    status: RunStatus
    portfolio_revision: int
    output: dict[str, Any]
    message: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "status": self.status.value,
            "portfolio_revision": self.portfolio_revision,
            "output": self.output,
            "message": self.message,
            "created_at": self.created_at,
        }
