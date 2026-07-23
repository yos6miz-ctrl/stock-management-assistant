from __future__ import annotations

import logging
from decimal import Decimal

from ..models import (
    MarketDataBatch,
    OpportunityScanBatch,
    PortfolioAnalysisBatch,
    PortfolioPerformance,
    PortfolioSnapshot,
    ProviderStatus,
    utc_now,
)


LOGGER = logging.getLogger(__name__)


class PlaceholderExternalProvider:
    """No-network provider used until real providers are explicitly configured."""

    def get_quotes(self, symbols: tuple[str, ...]) -> MarketDataBatch:
        LOGGER.info("Placeholder quote request for %d symbols", len(symbols))
        return MarketDataBatch(
            status=ProviderStatus.UNAVAILABLE,
            quotes=(),
            errors={
                symbol: "Live market-data provider is not configured."
                for symbol in symbols
            },
            requested_at=utc_now(),
            message="Live market-data provider is not configured.",
        )

    def analyze_portfolio(
        self,
        portfolio: PortfolioSnapshot,
        performance: PortfolioPerformance | None,
        previous_recommendations: dict[str, dict],
    ) -> PortfolioAnalysisBatch:
        LOGGER.info(
            "Placeholder portfolio-analysis request for %d positions",
            len(portfolio.positions),
        )
        return PortfolioAnalysisBatch(
            status=ProviderStatus.UNAVAILABLE,
            recommendations=(),
            researched_at=utc_now(),
            message=(
                "Fresh external portfolio research is unavailable because "
                "no research provider is configured."
            ),
        )

    def scan_market(
        self,
        excluded_symbols: frozenset[str],
        portfolio_value: Decimal | None,
    ) -> OpportunityScanBatch:
        LOGGER.info(
            "Placeholder market scan requested; %d symbols excluded",
            len(excluded_symbols),
        )
        return OpportunityScanBatch(
            status=ProviderStatus.UNAVAILABLE,
            candidates=(),
            researched_at=utc_now(),
            message=(
                "Fresh broad-market research is unavailable because no "
                "opportunity-research provider is configured."
            ),
        )
