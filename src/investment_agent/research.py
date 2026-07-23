from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .models import (
    Assessment,
    CONFIDENCE_LEVELS,
    HOLDING_ACTIONS,
    OPPORTUNITY_ACTIONS,
    SourceFact,
    ValidationError,
    normalize_symbol,
)


class ResearchProvider(Protocol):
    """Provider-neutral boundary for current external information."""

    def holding_bundle(self, symbol: str) -> dict[str, Any] | None:
        ...

    def opportunity_bundles(self) -> list[dict[str, Any]]:
        ...


class JsonResearchProvider:
    """Reads already-collected research packets without claiming live coverage."""

    def __init__(self, packet_path: str | Path):
        with Path(packet_path).open("r", encoding="utf-8") as packet_file:
            packet = json.load(packet_file)
        if not isinstance(packet, dict):
            raise ValidationError("research packet must be a JSON object")
        self.packet = packet

    def holding_bundle(self, symbol: str) -> dict[str, Any] | None:
        research = self.packet.get("portfolio_research", {})
        if not isinstance(research, dict):
            raise ValidationError("portfolio_research must be an object")
        bundle = research.get(normalize_symbol(symbol))
        if bundle is not None and not isinstance(bundle, dict):
            raise ValidationError(f"research bundle for {symbol} must be an object")
        return bundle

    def opportunity_bundles(self) -> list[dict[str, Any]]:
        opportunities = self.packet.get("opportunities", [])
        if not isinstance(opportunities, list):
            raise ValidationError("opportunities must be an array")
        if not all(isinstance(item, dict) for item in opportunities):
            raise ValidationError("every opportunity must be an object")
        return opportunities


def parse_bundle(
    subject: str,
    bundle: dict[str, Any],
    *,
    skill: str,
) -> tuple[tuple[SourceFact, ...], Assessment]:
    normalized = normalize_symbol(subject)
    raw_facts = bundle.get("facts")
    if not isinstance(raw_facts, list):
        raise ValidationError("bundle facts must be an array")
    facts = tuple(SourceFact.from_dict(normalized, item) for item in raw_facts)

    raw_assessment = bundle.get("assessment")
    if not isinstance(raw_assessment, dict):
        raise ValidationError("bundle assessment must be an object")

    action = _required_text(raw_assessment, "action").upper()
    allowed_actions = (
        HOLDING_ACTIONS if skill == "portfolio_research" else OPPORTUNITY_ACTIONS
    )
    if action not in allowed_actions:
        allowed = ", ".join(sorted(allowed_actions))
        raise ValidationError(f"action must be one of: {allowed}")

    confidence = _required_text(raw_assessment, "confidence").upper()
    if confidence not in CONFIDENCE_LEVELS:
        allowed = ", ".join(sorted(CONFIDENCE_LEVELS))
        raise ValidationError(f"confidence must be one of: {allowed}")

    meaningful = raw_assessment.get("meaningful")
    if not isinstance(meaningful, bool):
        raise ValidationError("meaningful must be a boolean")

    catalyst = raw_assessment.get("catalyst")
    if not isinstance(catalyst, dict):
        raise ValidationError("assessment catalyst must be an object")

    raw_indexes = raw_assessment.get("supporting_fact_indexes")
    if not isinstance(raw_indexes, list) or not all(
        isinstance(index, int) and not isinstance(index, bool) for index in raw_indexes
    ):
        raise ValidationError("supporting_fact_indexes must be an array of integers")
    if any(index < 0 or index >= len(facts) for index in raw_indexes):
        raise ValidationError("supporting_fact_indexes contains an invalid fact index")

    supporting_fact_ids = tuple(dict.fromkeys(facts[index].fact_id for index in raw_indexes))
    if meaningful and not supporting_fact_ids:
        raise ValidationError("meaningful analysis requires a supporting sourced fact")

    return facts, Assessment(
        subject=normalized,
        action=action,
        change_summary=_required_text(raw_assessment, "change_summary"),
        why_it_matters=_required_text(raw_assessment, "why_it_matters"),
        catalyst=_required_text(catalyst, "description"),
        catalyst_timing=_required_text(catalyst, "timing"),
        downside_risk=_required_text(raw_assessment, "downside_risk"),
        confidence=confidence,
        meaningful=meaningful,
        event_id=_required_text(raw_assessment, "event_id"),
        event_version=_required_text(raw_assessment, "event_version"),
        supporting_fact_ids=supporting_fact_ids,
    )


def _required_text(value: dict[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise ValidationError(f"{field} is required")
    return item.strip()
