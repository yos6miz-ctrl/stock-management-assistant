from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from investment_agent.models import (
    Catalyst,
    CatalystStatus,
    Confidence,
    EvidenceItem,
    EvidenceKind,
    HoldingRecommendation,
    MarketDataBatch,
    MarketQuote,
    OpportunityCandidate,
    OpportunityRating,
    OpportunityRiskClass,
    OpportunityScanBatch,
    PortfolioAnalysisBatch,
    ProviderStatus,
    QuoteStatus,
    RecommendationAction,
    RunStatus,
    SourceAuthority,
    SourceReference,
)
from investment_agent.providers import PlaceholderExternalProvider
from investment_agent.skills import (
    AggressiveShortTermOpportunityScannerSkill,
    PortfolioAnalysisAndRecommendationSkill,
    PortfolioTrackerSkill,
    ResearchValidationError,
)
from investment_agent.storage import JsonStateStore


AS_OF = "2026-07-23T12:00:00+00:00"


class StaticMarketDataProvider:
    def __init__(self, prices: dict[str, str]):
        self.prices = prices

    def get_quotes(self, symbols: tuple[str, ...]) -> MarketDataBatch:
        return MarketDataBatch(
            status=ProviderStatus.AVAILABLE,
            quotes=tuple(
                MarketQuote(
                    symbol=symbol,
                    price=Decimal(self.prices[symbol]),
                    as_of=AS_OF,
                    source="Test exchange feed",
                    status=QuoteStatus.LIVE,
                )
                for symbol in symbols
                if symbol in self.prices
            ),
            errors={
                symbol: "missing test quote"
                for symbol in symbols
                if symbol not in self.prices
            },
            requested_at=AS_OF,
            message="Test quotes.",
        )


class IncompleteMarketDataProvider(StaticMarketDataProvider):
    def get_quotes(self, symbols: tuple[str, ...]) -> MarketDataBatch:
        batch = super().get_quotes(symbols)
        return replace(
            batch,
            status=ProviderStatus.INCOMPLETE,
            message="The provider could not validate the complete request.",
        )


PRIMARY_SOURCE = SourceReference(
    publisher="Issuer filing",
    url="https://example.test/primary",
    retrieved_at=AS_OF,
    authority=SourceAuthority.PRIMARY,
)
SECOND_SOURCE = SourceReference(
    publisher="Independent data source",
    url="https://example.test/secondary",
    retrieved_at=AS_OF,
    authority=SourceAuthority.AUTHORITATIVE,
)
EVIDENCE = (
    EvidenceItem(
        statement="Fictitious test evidence.",
        kind=EvidenceKind.FACT,
        sources=(PRIMARY_SOURCE, SECOND_SOURCE),
        event_time=AS_OF,
    ),
)
CATALYST = Catalyst(
    event="Fictitious test catalyst",
    timing="Q4 2026",
    status=CatalystStatus.EXPECTED,
    sources=(PRIMARY_SOURCE, SECOND_SOURCE),
)


def recommendation(symbol: str) -> HoldingRecommendation:
    return HoldingRecommendation(
        symbol=symbol,
        action=RecommendationAction.HOLD,
        action_detail="Keep the test position unchanged.",
        why="Fictitious evidence supports no allocation change.",
        future_catalyst=CATALYST,
        change_condition="A measurable test milestone.",
        main_risk="Fictitious execution risk.",
        confidence=Confidence.MEDIUM,
        evidence=EVIDENCE,
        researched_at=AS_OF,
    )


class StaticPortfolioAnalysisProvider:
    def __init__(self, recommendations: tuple[HoldingRecommendation, ...]):
        self.recommendations = recommendations

    def analyze_portfolio(self, portfolio, performance, previous_recommendations):
        return PortfolioAnalysisBatch(
            status=ProviderStatus.AVAILABLE,
            recommendations=self.recommendations,
            researched_at=AS_OF,
            message="Fresh fictitious test research.",
        )


def opportunity(
    symbol: str,
    *,
    ranking_score: str = "8",
    maximum_position: str = "1",
) -> OpportunityCandidate:
    return OpportunityCandidate(
        symbol=symbol,
        rating=OpportunityRating.AGGRESSIVE_BUY,
        catalyst=CATALYST,
        why_it_may_move="A fictitious catalyst may change expectations.",
        why_it_may_be_mispriced="Fictitious test expectations differ.",
        entry_condition="Enter only after fictitious confirmation.",
        target_range="$12-$14 in this fictitious test.",
        exit_plan="Exit on a failed fictitious milestone.",
        holding_period="Two to eight weeks.",
        maximum_position_percent=Decimal(maximum_position),
        risk_class=OpportunityRiskClass.HIGH_RISK,
        main_risk="Fictitious catalyst failure.",
        confidence=Confidence.MEDIUM,
        expected_upside_percent=Decimal("25"),
        risk_score=4,
        ranking_score=Decimal(ranking_score),
        evidence=EVIDENCE,
        researched_at=AS_OF,
    )


class StaticOpportunityProvider:
    def __init__(self, candidates: tuple[OpportunityCandidate, ...]):
        self.candidates = candidates

    def scan_market(self, excluded_symbols, portfolio_value):
        return OpportunityScanBatch(
            status=ProviderStatus.AVAILABLE,
            candidates=self.candidates,
            researched_at=AS_OF,
            message="Fresh fictitious broad-market test research.",
        )


class SkillTests(unittest.TestCase):
    def make_store(self, directory: str) -> JsonStateStore:
        return JsonStateStore(Path(directory) / "state.json")

    def test_portfolio_tracker_calculates_position_and_total_performance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            tracker = PortfolioTrackerSkill(
                store,
                StaticMarketDataProvider({"AAA": "15", "BBB": "10"}),
            )
            tracker.add_position("AAA", "2", "10")
            tracker.add_position("BBB", "1", "20")

            result = tracker.run()
            performance = result.output["performance"]

            self.assertEqual(RunStatus.COMPLETE, result.status)
            self.assertEqual("40", performance["total_invested"])
            self.assertEqual("40", performance["current_value"])
            self.assertEqual("0", performance["profit_loss"])
            self.assertEqual("75", performance["positions"][0]["portfolio_weight_percent"])
            self.assertEqual("50", performance["positions"][0]["return_percent"])
            self.assertEqual("-50", performance["positions"][1]["return_percent"])

            changed_tracker = PortfolioTrackerSkill(
                store,
                StaticMarketDataProvider({"AAA": "18", "BBB": "10"}),
            )
            changed = changed_tracker.run().output["performance"]
            self.assertEqual(
                "20",
                changed["positions"][0]["change_since_previous"][
                    "price_change_percent"
                ],
            )

    def test_tracker_labels_saved_price_as_outdated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            live_tracker = PortfolioTrackerSkill(
                store,
                StaticMarketDataProvider({"AAA": "15"}),
            )
            live_tracker.add_position("AAA", "2", "10")
            live_tracker.run()

            offline_tracker = PortfolioTrackerSkill(
                store,
                PlaceholderExternalProvider(),
            )
            result = offline_tracker.run()
            position = result.output["performance"]["positions"][0]

            self.assertEqual(RunStatus.PARTIAL, result.status)
            self.assertEqual("outdated", position["quote"]["status"])
            self.assertIn("outdated", position["market_data_note"])

    def test_tracker_does_not_accept_incomplete_provider_run_as_complete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            tracker = PortfolioTrackerSkill(
                store,
                IncompleteMarketDataProvider({"AAA": "15"}),
            )
            tracker.add_position("AAA", "2", "10")

            result = tracker.run()

            self.assertEqual(RunStatus.PARTIAL, result.status)

    def test_portfolio_analysis_covers_every_holding_without_mutating_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            tracker = PortfolioTrackerSkill(
                store,
                PlaceholderExternalProvider(),
            )
            tracker.add_position("AAA", "1", "10")
            before = tracker.get_portfolio_snapshot().to_dict()
            skill = PortfolioAnalysisAndRecommendationSkill(
                tracker,
                tracker,
                StaticPortfolioAnalysisProvider((recommendation("AAA"),)),
                store,
            )

            result = skill.run()

            self.assertEqual(RunStatus.COMPLETE, result.status)
            self.assertEqual("hold", result.output["recommendations"][0]["action"])
            self.assertEqual(
                before,
                tracker.get_portfolio_snapshot().to_dict()
                | {"generated_at": before["generated_at"]},
            )

    def test_portfolio_analysis_rejects_missing_holding_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            tracker = PortfolioTrackerSkill(
                store,
                PlaceholderExternalProvider(),
            )
            tracker.add_position("AAA", "1", "10")
            skill = PortfolioAnalysisAndRecommendationSkill(
                tracker,
                tracker,
                StaticPortfolioAnalysisProvider(()),
                store,
            )

            with self.assertRaises(ResearchValidationError):
                skill.run()

    def test_portfolio_analysis_rejects_single_source_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            tracker = PortfolioTrackerSkill(
                store,
                PlaceholderExternalProvider(),
            )
            tracker.add_position("AAA", "1", "10")
            single_source_evidence = (
                replace(EVIDENCE[0], sources=(PRIMARY_SOURCE,)),
            )
            unsupported = replace(
                recommendation("AAA"),
                evidence=single_source_evidence,
                future_catalyst=replace(
                    CATALYST,
                    sources=(PRIMARY_SOURCE,),
                ),
            )
            skill = PortfolioAnalysisAndRecommendationSkill(
                tracker,
                tracker,
                StaticPortfolioAnalysisProvider((unsupported,)),
                store,
            )

            with self.assertRaises(ResearchValidationError):
                skill.run()

    def test_opportunity_scanner_excludes_holdings_and_limits_output_to_five(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            tracker = PortfolioTrackerSkill(
                store,
                PlaceholderExternalProvider(),
            )
            tracker.add_position("HELD", "1", "10")
            candidates = (
                opportunity("HELD", ranking_score="20"),
                *(opportunity(f"NEW{index}", ranking_score=str(index)) for index in range(6)),
            )
            skill = AggressiveShortTermOpportunityScannerSkill(
                tracker,
                tracker,
                StaticOpportunityProvider(tuple(candidates)),
                store,
            )

            result = skill.run()
            symbols = {
                candidate["symbol"] for candidate in result.output["candidates"]
            }

            self.assertEqual(5, len(symbols))
            self.assertNotIn("HELD", symbols)
            self.assertEqual(
                {"HELD"},
                {
                    position.symbol
                    for position in tracker.get_portfolio_snapshot().positions
                },
            )

    def test_opportunity_scanner_rejects_excessive_position_size(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            tracker = PortfolioTrackerSkill(
                store,
                PlaceholderExternalProvider(),
            )
            skill = AggressiveShortTermOpportunityScannerSkill(
                tracker,
                tracker,
                StaticOpportunityProvider(
                    (opportunity("NEW", maximum_position="4"),)
                ),
                store,
            )

            with self.assertRaises(ResearchValidationError):
                skill.run()

    def test_opportunity_scanner_rejects_rumor_based_aggressive_buy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.make_store(temporary_directory)
            tracker = PortfolioTrackerSkill(
                store,
                PlaceholderExternalProvider(),
            )
            rumored = replace(
                opportunity("NEW"),
                catalyst=replace(
                    CATALYST,
                    status=CatalystStatus.RUMORED,
                ),
            )
            skill = AggressiveShortTermOpportunityScannerSkill(
                tracker,
                tracker,
                StaticOpportunityProvider((rumored,)),
                store,
            )

            with self.assertRaises(ResearchValidationError):
                skill.run()


if __name__ == "__main__":
    unittest.main()
