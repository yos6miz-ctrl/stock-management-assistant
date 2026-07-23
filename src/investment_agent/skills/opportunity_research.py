from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable

from ..formatting import format_percent, title_enum
from ..interfaces import (
    OpportunityResearchProvider,
    PortfolioPerformanceProvider,
    PortfolioSnapshotProvider,
)
from ..models import (
    CatalystStatus,
    EvidenceKind,
    OpportunityCandidate,
    OpportunityRating,
    OpportunityRiskClass,
    ProviderStatus,
    RunStatus,
    SkillRunResult,
    SourceAuthority,
    normalize_symbol,
    utc_now,
)
from ..storage import JsonStateStore
from .portfolio_research import ResearchValidationError


LOGGER = logging.getLogger(__name__)


class AggressiveShortTermOpportunityScannerSkill:
    """Skill 3: validated, ranked, catalyst-backed market opportunities."""

    name = "aggressive_short_term_opportunity_scanner"

    def __init__(
        self,
        portfolio: PortfolioSnapshotProvider,
        performance: PortfolioPerformanceProvider,
        research_provider: OpportunityResearchProvider,
        store: JsonStateStore,
    ):
        self.portfolio = portfolio
        self.performance = performance
        self.research_provider = research_provider
        self.store = store

    def run(self) -> SkillRunResult:
        snapshot = self.portfolio.get_portfolio_snapshot()
        latest_performance = self.performance.get_latest_performance()
        excluded = frozenset(position.symbol for position in snapshot.positions)
        portfolio_value = (
            latest_performance.current_value if latest_performance else None
        )
        batch = self.research_provider.scan_market(excluded, portfolio_value)

        if batch.status != ProviderStatus.AVAILABLE:
            run_status = (
                RunStatus.PARTIAL
                if batch.status == ProviderStatus.INCOMPLETE
                else RunStatus.UNAVAILABLE
            )
            output = {
                "best_opportunity_now": (
                    "None — fresh research was not fully validated."
                ),
                "highest_upside_opportunity": "None.",
                "highest_risk_opportunity": "None.",
                "recommended_number_of_new_positions": 0,
                "candidates": [],
                "prioritized_actions": [],
                "researched_at": batch.researched_at,
            }
            result = SkillRunResult(
                skill=self.name,
                status=run_status,
                portfolio_revision=snapshot.revision,
                output=output,
                message=batch.message,
                created_at=utc_now(),
            )
            self.store.record_opportunity_scan(output)
            self.store.record_skill_run(result.to_dict())
            return result

        if not batch.researched_at.strip():
            raise ResearchValidationError(
                "opportunity research run timestamp is required"
            )
        validated = self._validate_candidates(batch.candidates, excluded)
        ranked = tuple(
            sorted(
                validated,
                key=lambda item: (item.ranking_score, item.symbol),
                reverse=True,
            )[:5]
        )
        best = ranked[0] if ranked else None
        highest_upside = (
            max(ranked, key=lambda item: item.expected_upside_percent)
            if ranked
            else None
        )
        highest_risk = (
            max(ranked, key=lambda item: item.risk_score) if ranked else None
        )
        buys = [
            item
            for item in ranked
            if item.rating == OpportunityRating.AGGRESSIVE_BUY
        ]
        output = {
            "best_opportunity_now": best.symbol if best else "None.",
            "highest_upside_opportunity": (
                highest_upside.symbol if highest_upside else "None."
            ),
            "highest_risk_opportunity": (
                highest_risk.symbol if highest_risk else "None."
            ),
            "recommended_number_of_new_positions": len(buys),
            "candidates": [item.to_dict() for item in ranked],
            "prioritized_actions": [
                (
                    f"Best action now: follow {best.entry_condition}"
                    if best
                    else "Best action now: no qualifying opportunity."
                ),
                (
                    "Closest catalyst: "
                    f"{best.catalyst.event} — {best.catalyst.timing}"
                    if best
                    else "Closest catalyst: none."
                ),
                (
                    f"Watchlist: {ranked[-1].symbol}"
                    if ranked
                    else "Watchlist: none."
                ),
            ],
            "researched_at": batch.researched_at,
        }
        result = SkillRunResult(
            skill=self.name,
            status=RunStatus.COMPLETE,
            portfolio_revision=snapshot.revision,
            output=output,
            message=batch.message,
            created_at=utc_now(),
        )
        self.store.record_opportunity_scan(output)
        self.store.record_skill_run(result.to_dict())
        return result

    def format_result(self, result: SkillRunResult) -> str:
        output = result.output
        lines = [
            f"**Best opportunity now:** {output['best_opportunity_now']}",
            (
                "**Highest-upside opportunity:** "
                f"{output['highest_upside_opportunity']}"
            ),
            (
                "**Highest-risk opportunity:** "
                f"{output['highest_risk_opportunity']}"
            ),
            (
                "**Recommended number of new positions:** "
                f"{output['recommended_number_of_new_positions']}"
            ),
        ]
        for index, item in enumerate(output["candidates"], start=1):
            catalyst = item["catalyst"]
            lines.extend(
                [
                    "",
                    (
                        f"### {index}. {item['symbol']} — "
                        f"{title_enum(item['rating'])}"
                    ),
                    (
                        "* **Catalyst:** "
                        f"{catalyst['event']} — {catalyst['timing']} "
                        f"({title_enum(catalyst['status'])})"
                    ),
                    f"* **Why it may move:** {item['why_it_may_move']}",
                    (
                        "* **Why it may be mispriced:** "
                        f"{item['why_it_may_be_mispriced']}"
                    ),
                    f"* **Entry:** {item['entry_condition']}",
                    f"* **Target:** {item['target_range']}",
                    f"* **Exit:** {item['exit_plan']}",
                    f"* **Holding period:** {item['holding_period']}",
                    (
                        "* **Maximum position:** "
                        f"{format_percent(Decimal(item['maximum_position_percent']))}"
                    ),
                    f"* **Main risk:** {item['main_risk']}",
                    f"* **Confidence:** {title_enum(item['confidence'])}",
                ]
            )
        lines.append("")
        lines.extend(
            f"{index}. {action}"
            for index, action in enumerate(
                output["prioritized_actions"], start=1
            )
        )
        return "\n".join(lines)

    def _validate_candidates(
        self,
        candidates: Iterable[OpportunityCandidate],
        excluded_symbols: frozenset[str],
    ) -> tuple[OpportunityCandidate, ...]:
        validated = []
        seen = set()
        for item in candidates:
            symbol = normalize_symbol(item.symbol)
            if symbol in excluded_symbols:
                continue
            if symbol in seen:
                raise ResearchValidationError(
                    f"duplicate opportunity candidate {symbol}"
                )
            seen.add(symbol)
            self._require_text(item.why_it_may_move, "why it may move", symbol)
            self._require_text(
                item.why_it_may_be_mispriced,
                "why it may be mispriced",
                symbol,
            )
            self._require_text(item.entry_condition, "entry condition", symbol)
            self._require_text(item.target_range, "target range", symbol)
            self._require_text(item.exit_plan, "exit plan", symbol)
            self._require_text(item.holding_period, "holding period", symbol)
            self._require_text(item.main_risk, "main risk", symbol)
            self._require_text(item.researched_at, "researched_at", symbol)
            self._require_text(item.catalyst.event, "catalyst event", symbol)
            self._require_text(item.catalyst.timing, "catalyst timing", symbol)
            if item.catalyst.status == CatalystStatus.UNKNOWN:
                raise ResearchValidationError(
                    f"{symbol} catalyst status is unknown"
                )
            if (
                item.rating == OpportunityRating.AGGRESSIVE_BUY
                and item.catalyst.status == CatalystStatus.RUMORED
            ):
                raise ResearchValidationError(
                    f"{symbol} cannot be an Aggressive Buy based on a rumor"
                )
            self._validate_position_size(item)
            if not 1 <= item.risk_score <= 5:
                raise ResearchValidationError(
                    f"{symbol} risk_score must be between 1 and 5"
                )
            if item.ranking_score < 0:
                raise ResearchValidationError(
                    f"{symbol} ranking_score cannot be negative"
                )
            self._validate_sources(item)
            validated.append(item)
        return tuple(validated)

    @staticmethod
    def _validate_position_size(item: OpportunityCandidate) -> None:
        limits = {
            OpportunityRiskClass.LOWER_RISK_AGGRESSIVE: Decimal("5"),
            OpportunityRiskClass.HIGH_RISK: Decimal("3"),
            OpportunityRiskClass.BINARY_SPECULATIVE: Decimal("1.5"),
        }
        maximum = limits[item.risk_class]
        if item.maximum_position_percent < 0:
            raise ResearchValidationError(
                f"{item.symbol} maximum position cannot be negative"
            )
        if (
            item.rating == OpportunityRating.AGGRESSIVE_BUY
            and item.maximum_position_percent == 0
        ):
            raise ResearchValidationError(
                f"{item.symbol} Aggressive Buy requires a non-zero maximum position"
            )
        if item.maximum_position_percent > maximum:
            raise ResearchValidationError(
                f"{item.symbol} maximum position exceeds {maximum}% "
                f"for {item.risk_class.value}"
            )

    @staticmethod
    def _validate_sources(item: OpportunityCandidate) -> None:
        if not item.evidence:
            raise ResearchValidationError(
                f"{item.symbol} requires explicit supporting evidence"
            )
        if not any(
            evidence.kind
            in {
                EvidenceKind.FACT,
                EvidenceKind.MANAGEMENT_CLAIM,
                EvidenceKind.ESTIMATE,
            }
            for evidence in item.evidence
        ):
            raise ResearchValidationError(
                f"{item.symbol} cannot rely only on rumors or conclusions"
            )
        sources = [
            source
            for evidence in item.evidence
            for source in evidence.sources
        ] + list(item.catalyst.sources)
        urls = {source.url for source in sources if source.url}
        publishers = {
            source.publisher.strip().casefold()
            for source in sources
            if source.publisher.strip()
        }
        if len(urls) < 2 or len(publishers) < 2:
            raise ResearchValidationError(
                f"{item.symbol} requires at least two independent sources"
            )
        if not any(
            source.authority
            in {SourceAuthority.PRIMARY, SourceAuthority.AUTHORITATIVE}
            for source in sources
        ):
            raise ResearchValidationError(
                f"{item.symbol} requires a primary or authoritative source"
            )

    @staticmethod
    def _require_text(value: str, field: str, symbol: str) -> None:
        if not value.strip():
            raise ResearchValidationError(f"{symbol} {field} is required")
