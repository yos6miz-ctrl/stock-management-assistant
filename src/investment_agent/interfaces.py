from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from .models import (
    MarketDataBatch,
    OpportunityScanBatch,
    PortfolioAnalysisBatch,
    PortfolioPerformance,
    PortfolioSnapshot,
    SkillRunResult,
)


class PortfolioSnapshotProvider(Protocol):
    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        ...


class PortfolioPerformanceProvider(Protocol):
    def get_latest_performance(self) -> PortfolioPerformance | None:
        ...


class MarketDataProvider(Protocol):
    def get_quotes(self, symbols: tuple[str, ...]) -> MarketDataBatch:
        ...


class PortfolioAnalysisProvider(Protocol):
    def analyze_portfolio(
        self,
        portfolio: PortfolioSnapshot,
        performance: PortfolioPerformance | None,
        previous_recommendations: dict[str, dict],
    ) -> PortfolioAnalysisBatch:
        ...


class OpportunityResearchProvider(Protocol):
    def scan_market(
        self,
        excluded_symbols: frozenset[str],
        portfolio_value: Decimal | None,
    ) -> OpportunityScanBatch:
        ...


class RunnableSkill(Protocol):
    name: str

    def run(self) -> SkillRunResult:
        ...
