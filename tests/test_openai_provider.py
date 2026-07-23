from __future__ import annotations

import json
import unittest

from investment_agent.models import (
    OpportunityRating,
    ProviderStatus,
    RecommendationAction,
)
from investment_agent.providers import OpenAIResearchProvider
from investment_agent.storage import JsonStateStore


NOW = "2026-07-23T12:00:00+00:00"


def source(publisher: str, url: str, authority: str) -> dict:
    return {
        "publisher": publisher,
        "url": url,
        "retrieved_at": NOW,
        "authority": authority,
    }


class CapturingRequest:
    def __init__(self, value: dict):
        self.value = value
        self.payloads = []

    def __call__(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(self.value),
                        }
                    ],
                }
            ],
        }


class OpenAIProviderTests(unittest.TestCase):
    def test_quotes_use_web_search_and_strict_structured_output(self) -> None:
        request = CapturingRequest(
            {
                "complete": True,
                "message": "Current quote confirmed.",
                "quotes": [
                    {
                        "symbol": "AAA",
                        "price": 12.5,
                        "as_of": NOW,
                        "source_name": "Test exchange",
                        "source_url": "https://example.test/quote",
                        "status": "live",
                        "currency": "USD",
                    }
                ],
                "errors": [],
            }
        )
        provider = OpenAIResearchProvider(
            "test-key",
            request_fn=request,
        )

        result = provider.get_quotes(("AAA",))

        self.assertEqual(ProviderStatus.AVAILABLE, result.status)
        self.assertEqual("12.5", str(result.quotes[0].price))
        payload = request.payloads[0]
        self.assertEqual("web_search", payload["tools"][0]["type"])
        self.assertEqual("required", payload["tool_choice"])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual("json_schema", payload["text"]["format"]["type"])

    def test_portfolio_recommendation_maps_structured_sources(self) -> None:
        primary = source(
            "Issuer",
            "https://example.test/filing",
            "primary",
        )
        secondary = source(
            "Regulator",
            "https://example.test/regulator",
            "authoritative",
        )
        request = CapturingRequest(
            {
                "complete": True,
                "message": "Fresh research complete.",
                "researched_at": NOW,
                "recommendations": [
                    {
                        "symbol": "AAA",
                        "action": "hold",
                        "action_detail": "Keep the position unchanged.",
                        "why": "The test thesis remains intact.",
                        "future_catalyst": {
                            "event": "Test filing",
                            "timing": "Q4 2026",
                            "status": "expected",
                            "sources": [primary, secondary],
                        },
                        "change_condition": "A measurable test miss.",
                        "main_risk": "Test execution risk.",
                        "confidence": "medium",
                        "evidence": [
                            {
                                "statement": "Test fact.",
                                "kind": "fact",
                                "event_time": NOW,
                                "sources": [primary, secondary],
                            }
                        ],
                        "researched_at": NOW,
                    }
                ],
            }
        )
        provider = OpenAIResearchProvider("test-key", request_fn=request)
        with self.subTest("portfolio model"):
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as directory:
                store = JsonStateStore(Path(directory) / "state.json")
                store.add_position("AAA", "1", "10")
                portfolio = store.get_portfolio_snapshot()

                result = provider.analyze_portfolio(portfolio, None, {})

        self.assertEqual(ProviderStatus.AVAILABLE, result.status)
        self.assertEqual(
            RecommendationAction.HOLD,
            result.recommendations[0].action,
        )
        self.assertEqual(
            "https://example.test/filing",
            result.recommendations[0].evidence[0].sources[0].url,
        )

    def test_opportunity_scan_maps_structured_catalyst_and_exit_plan(self) -> None:
        primary = source(
            "Issuer",
            "https://example.test/issuer",
            "primary",
        )
        secondary = source(
            "Regulator",
            "https://example.test/decision",
            "authoritative",
        )
        request = CapturingRequest(
            {
                "complete": True,
                "message": "Broad scan complete.",
                "researched_at": NOW,
                "candidates": [
                    {
                        "symbol": "NEW",
                        "rating": "aggressive_buy",
                        "catalyst": {
                            "event": "Test regulatory decision",
                            "timing": "2026-10-15",
                            "status": "confirmed",
                            "sources": [primary, secondary],
                        },
                        "why_it_may_move": "The test decision may reprice it.",
                        "why_it_may_be_mispriced": "Test estimates may be low.",
                        "entry_condition": "Enter only after test confirmation.",
                        "target_range": "$12-$14 in this test.",
                        "exit_plan": "Exit if the test decision is negative.",
                        "holding_period": "Two to eight weeks.",
                        "maximum_position_percent": 1,
                        "risk_class": "binary_speculative",
                        "main_risk": "Binary test failure.",
                        "confidence": "medium",
                        "expected_upside_percent": 25,
                        "risk_score": 5,
                        "ranking_score": 8,
                        "evidence": [
                            {
                                "statement": "Test fact.",
                                "kind": "fact",
                                "event_time": NOW,
                                "sources": [primary, secondary],
                            }
                        ],
                        "researched_at": NOW,
                    }
                ],
            }
        )
        provider = OpenAIResearchProvider("test-key", request_fn=request)

        result = provider.scan_market(frozenset({"HELD"}), None)

        self.assertEqual(ProviderStatus.AVAILABLE, result.status)
        self.assertEqual(
            OpportunityRating.AGGRESSIVE_BUY,
            result.candidates[0].rating,
        )
        self.assertIn("negative", result.candidates[0].exit_plan)


if __name__ == "__main__":
    unittest.main()
