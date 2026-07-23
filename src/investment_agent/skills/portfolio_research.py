from __future__ import annotations

import logging
from collections import Counter
from typing import Iterable

from ..formatting import title_enum
from ..interfaces import (
    PortfolioAnalysisProvider,
    PortfolioPerformanceProvider,
    PortfolioSnapshotProvider,
)
from ..models import (
    CatalystStatus,
    EvidenceKind,
    HoldingRecommendation,
    ProviderStatus,
    RecommendationAction,
    RunStatus,
    SkillRunResult,
    SourceAuthority,
    normalize_symbol,
    utc_now,
)
from ..storage import JsonStateStore


LOGGER = logging.getLogger(__name__)


class ResearchValidationError(ValueError):
    """Raised when provider research is incomplete or unsupported."""


class PortfolioAnalysisAndRecommendationSkill:
    """Skill 2: validated recommendations for current holdings only."""

    name = "portfolio_analysis_and_recommendation"

    def __init__(
        self,
        portfolio: PortfolioSnapshotProvider,
        performance: PortfolioPerformanceProvider,
        research_provider: PortfolioAnalysisProvider,
        store: JsonStateStore,
    ):
        self.portfolio = portfolio
        self.performance = performance
        self.research_provider = research_provider
        self.store = store

    def run(self) -> SkillRunResult:
        snapshot = self.portfolio.get_portfolio_snapshot()
        latest_performance = self.performance.get_latest_performance()
        previous = self.store.previous_recommendations()
        batch = self.research_provider.analyze_portfolio(
            snapshot,
            latest_performance,
            previous,
        )

        if batch.status != ProviderStatus.AVAILABLE:
            run_status = (
                RunStatus.PARTIAL
                if batch.status == ProviderStatus.INCOMPLETE
                else RunStatus.UNAVAILABLE
            )
            output = {
                "portfolio_conclusion": batch.message,
                "most_important_action": (
                    "No action: fresh research was not fully validated."
                ),
                "most_important_catalyst": "Not validated.",
                "recommendations": [],
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
            self.store.record_portfolio_analysis(output)
            self.store.record_skill_run(result.to_dict())
            return result

        if not batch.researched_at.strip():
            raise ResearchValidationError(
                "portfolio research run timestamp is required"
            )
        recommendations = self._validate_recommendations(
            batch.recommendations,
            {position.symbol for position in snapshot.positions},
        )
        ordered = sorted(
            recommendations,
            key=lambda item: (
                self._action_priority(item.action),
                item.symbol,
            ),
        )
        action_counts = Counter(item.action.value for item in ordered)
        conclusion = (
            "Every holding received fresh evidence-based review: "
            + ", ".join(
                f"{count} {title_enum(action)}"
                for action, count in sorted(action_counts.items())
            )
            + "."
        )
        important = ordered[0] if ordered else None
        output = {
            "portfolio_conclusion": conclusion,
            "most_important_action": (
                f"{important.symbol}: {title_enum(important.action.value)}"
                if important
                else "No holdings to analyze."
            ),
            "most_important_catalyst": (
                f"{important.future_catalyst.event} — "
                f"{important.future_catalyst.timing} "
                f"({important.future_catalyst.status.value})"
                if important
                else "None."
            ),
            "recommendations": [item.to_dict() for item in ordered],
            "prioritized_actions": [
                f"{item.symbol}: {item.action_detail}" for item in ordered[:3]
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
        self.store.record_portfolio_analysis(output)
        self.store.record_skill_run(result.to_dict())
        return result

    def format_result(self, result: SkillRunResult) -> str:
        output = result.output
        lines = [
            output["portfolio_conclusion"],
            f"Most important action: {output['most_important_action']}",
            f"Most important upcoming catalyst: {output['most_important_catalyst']}",
        ]
        for item in output["recommendations"]:
            catalyst = item["future_catalyst"]
            lines.extend(
                [
                    "",
                    (
                        f"### {item['symbol']} — "
                        f"{title_enum(item['action'])}"
                    ),
                    f"* **Action:** {item['action_detail']}",
                    f"* **Why:** {item['why']}",
                    (
                        "* **Future catalyst:** "
                        f"{catalyst['event']} — {catalyst['timing']} "
                        f"({title_enum(catalyst['status'])})"
                    ),
                    (
                        "* **What could change the recommendation:** "
                        f"{item['change_condition']}"
                    ),
                    f"* **Main risk:** {item['main_risk']}",
                    f"* **Confidence:** {title_enum(item['confidence'])}",
                ]
            )
        if output["prioritized_actions"]:
            lines.append("")
            for index, action in enumerate(
                output["prioritized_actions"], start=1
            ):
                lines.append(f"{index}. {action}")
        return "\n".join(lines)

    def _validate_recommendations(
        self,
        recommendations: Iterable[HoldingRecommendation],
        held_symbols: set[str],
    ) -> tuple[HoldingRecommendation, ...]:
        items = tuple(recommendations)
        symbols = [normalize_symbol(item.symbol) for item in items]
        if len(symbols) != len(set(symbols)):
            raise ResearchValidationError(
                "provider returned duplicate holding recommendations"
            )
        if set(symbols) != held_symbols:
            missing = held_symbols - set(symbols)
            extra = set(symbols) - held_symbols
            raise ResearchValidationError(
                f"recommendations must match holdings; missing={sorted(missing)}, "
                f"extra={sorted(extra)}"
            )

        for item in items:
            if item.action == RecommendationAction.NOT_EVALUATED:
                raise ResearchValidationError(
                    f"{item.symbol} has no recommendation"
                )
            self._require_text(item.action_detail, "action_detail", item.symbol)
            self._require_text(item.why, "why", item.symbol)
            self._require_text(
                item.change_condition, "change_condition", item.symbol
            )
            self._require_text(item.main_risk, "main_risk", item.symbol)
            self._require_text(
                item.researched_at, "researched_at", item.symbol
            )
            self._require_text(
                item.future_catalyst.event, "catalyst event", item.symbol
            )
            self._require_text(
                item.future_catalyst.timing, "catalyst timing", item.symbol
            )
            if item.future_catalyst.status == CatalystStatus.UNKNOWN:
                raise ResearchValidationError(
                    f"{item.symbol} catalyst status is unknown"
                )
            self._validate_evidence(
                item.symbol,
                item.evidence,
                item.future_catalyst.sources,
            )
        return items

    @staticmethod
    def _validate_evidence(symbol: str, evidence, catalyst_sources) -> None:
        if not evidence:
            raise ResearchValidationError(
                f"{symbol} requires explicit supporting evidence"
            )
        if not any(
            item.kind
            in {
                EvidenceKind.FACT,
                EvidenceKind.MANAGEMENT_CLAIM,
                EvidenceKind.ESTIMATE,
            }
            for item in evidence
        ):
            raise ResearchValidationError(
                f"{symbol} cannot rely only on rumors or conclusions"
            )
        sources = [
            source
            for item in evidence
            for source in item.sources
        ] + list(catalyst_sources)
        unique_urls = {source.url for source in sources if source.url}
        unique_publishers = {
            source.publisher.strip().casefold()
            for source in sources
            if source.publisher.strip()
        }
        if len(unique_urls) < 2 or len(unique_publishers) < 2:
            raise ResearchValidationError(
                f"{symbol} requires at least two independent sources"
            )
        if not any(
            source.authority
            in {SourceAuthority.PRIMARY, SourceAuthority.AUTHORITATIVE}
            for source in sources
        ):
            raise ResearchValidationError(
                f"{symbol} requires a primary or authoritative source"
            )

    @staticmethod
    def _require_text(value: str, field: str, symbol: str) -> None:
        if not value.strip():
            raise ResearchValidationError(f"{symbol} {field} is required")

    @staticmethod
    def _action_priority(action: RecommendationAction) -> int:
        return {
            RecommendationAction.SELL: 0,
            RecommendationAction.REDUCE: 1,
            RecommendationAction.BUY_MORE: 2,
            RecommendationAction.HOLD: 3,
            RecommendationAction.NOT_EVALUATED: 4,
        }[action]
