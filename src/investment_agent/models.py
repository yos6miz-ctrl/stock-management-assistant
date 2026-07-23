from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse


CONFIRMATION_STATES = {"confirmed", "unconfirmed", "conflicting"}
CONFIDENCE_LEVELS = {"LOW", "MEDIUM", "HIGH"}
HOLDING_ACTIONS = {"BUY", "HOLD", "SELL", "WAIT"}
OPPORTUNITY_ACTIONS = {"BUY", "WATCH", "REJECT"}


class ValidationError(ValueError):
    """Raised when supplied portfolio or research data is unsafe to use."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not symbol or len(symbol) > 32:
        raise ValidationError("symbol must contain between 1 and 32 characters")
    if any(character.isspace() for character in symbol):
        raise ValidationError("symbol cannot contain whitespace")
    return symbol


def positive_decimal(value: str | int | float | Decimal, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(f"{field} must be a decimal number") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValidationError(f"{field} must be greater than zero")
    return parsed


def decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: Decimal
    average_price: Decimal
    notes: str
    revision: int
    created_at: str
    updated_at: str

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.average_price

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": decimal_text(self.quantity),
            "average_price": decimal_text(self.average_price),
            "cost_basis": decimal_text(self.cost_basis),
            "notes": self.notes,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class PortfolioSnapshot:
    revision: int
    positions: tuple[Position, ...]

    def as_dict(self) -> dict[str, Any]:
        total_cost = sum(
            (position.cost_basis for position in self.positions), Decimal("0")
        )
        return {
            "revision": self.revision,
            "positions": [position.as_dict() for position in self.positions],
            "position_count": len(self.positions),
            "total_cost_basis": decimal_text(total_cost),
        }


@dataclass(frozen=True)
class SourceFact:
    subject: str
    category: str
    title: str
    detail: str
    event_time: str
    confirmation: str
    publisher: str
    source_url: str
    retrieved_at: str

    @classmethod
    def from_dict(cls, subject: str, value: dict[str, Any]) -> "SourceFact":
        source = value.get("source")
        if not isinstance(source, dict):
            raise ValidationError("every fact requires a source object")

        fields = {
            "category": value.get("category"),
            "title": value.get("title"),
            "detail": value.get("detail"),
            "event_time": value.get("event_time"),
            "confirmation": value.get("confirmation"),
            "publisher": source.get("publisher"),
            "source_url": source.get("url"),
            "retrieved_at": source.get("retrieved_at"),
        }
        for name, item in fields.items():
            if not isinstance(item, str) or not item.strip():
                raise ValidationError(f"fact field {name} is required")

        confirmation = fields["confirmation"].strip().lower()
        if confirmation not in CONFIRMATION_STATES:
            allowed = ", ".join(sorted(CONFIRMATION_STATES))
            raise ValidationError(f"confirmation must be one of: {allowed}")

        parsed_url = urlparse(fields["source_url"].strip())
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValidationError("fact source URL must be an absolute HTTP(S) URL")

        return cls(
            subject=normalize_symbol(subject),
            category=fields["category"].strip(),
            title=fields["title"].strip(),
            detail=fields["detail"].strip(),
            event_time=fields["event_time"].strip(),
            confirmation=confirmation,
            publisher=fields["publisher"].strip(),
            source_url=fields["source_url"].strip(),
            retrieved_at=fields["retrieved_at"].strip(),
        )

    @property
    def fact_id(self) -> str:
        canonical = json.dumps(
            {
                "subject": self.subject,
                "category": self.category,
                "title": self.title,
                "detail": self.detail,
                "event_time": self.event_time,
                "publisher": self.publisher,
                "source_url": self.source_url,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "subject": self.subject,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "event_time": self.event_time,
            "confirmation": self.confirmation,
            "source": {
                "publisher": self.publisher,
                "url": self.source_url,
                "retrieved_at": self.retrieved_at,
            },
        }


@dataclass(frozen=True)
class Assessment:
    subject: str
    action: str
    change_summary: str
    why_it_matters: str
    catalyst: str
    catalyst_timing: str
    downside_risk: str
    confidence: str
    meaningful: bool
    event_id: str
    event_version: str
    supporting_fact_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "action": self.action,
            "change_summary": self.change_summary,
            "why_it_matters": self.why_it_matters,
            "catalyst": {
                "description": self.catalyst,
                "timing": self.catalyst_timing,
            },
            "downside_risk": self.downside_risk,
            "confidence": self.confidence,
            "meaningful": self.meaningful,
            "event_id": self.event_id,
            "event_version": self.event_version,
            "supporting_fact_ids": list(self.supporting_fact_ids),
        }
