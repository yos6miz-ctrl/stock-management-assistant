from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from investment_agent.alerts import MemoryAlertSink
from investment_agent.research import JsonResearchProvider
from investment_agent.skills import (
    PortfolioManagement,
    run_opportunity_research,
    run_portfolio_research,
)
from investment_agent.store import StateStore


def fact(title: str = "Material filing") -> dict:
    return {
        "category": "filing",
        "title": title,
        "detail": "A sourced factual development.",
        "event_time": "2026-01-01T00:00:00Z",
        "confirmation": "confirmed",
        "source": {
            "publisher": "Primary source",
            "url": "https://example.test/filing",
            "retrieved_at": "2026-01-01T01:00:00Z",
        },
    }


def assessment(
    *,
    action: str = "HOLD",
    meaningful: bool = True,
    event_id: str = "event-1",
    event_version: str = "v1",
) -> dict:
    return {
        "action": action,
        "change_summary": "A material fact changed.",
        "why_it_matters": "It can affect the investment case.",
        "catalyst": {
            "description": "A specific next catalyst.",
            "timing": "Timing supplied by the sourced research.",
        },
        "downside_risk": "The main identified downside risk.",
        "confidence": "MEDIUM",
        "meaningful": meaningful,
        "event_id": event_id,
        "event_version": event_version,
        "supporting_fact_indexes": [0],
    }


class AgentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database = self.root / "agent.db"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def provider(self, packet: dict) -> JsonResearchProvider:
        packet_path = self.root / "packet.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        return JsonResearchProvider(packet_path)

    def test_portfolio_persists_changes_and_cost_basis(self) -> None:
        with StateStore(self.database) as store:
            skill = PortfolioManagement(store)
            added = skill.add("test", "2.5", "10.20", "note")
            self.assertEqual("25.5", added.as_dict()["cost_basis"])
            updated = skill.update("TEST", quantity="3")
            self.assertEqual("30.6", updated.as_dict()["cost_basis"])

        with StateStore(self.database) as reopened:
            snapshot = PortfolioManagement(reopened).current()
            self.assertEqual(2, snapshot["revision"])
            self.assertEqual("TEST", snapshot["positions"][0]["symbol"])
            self.assertEqual(2, len(reopened.portfolio_history()))

            PortfolioManagement(reopened).remove("TEST")
            self.assertEqual(0, reopened.portfolio_snapshot().as_dict()["position_count"])

    def test_portfolio_research_alerts_once_and_separates_facts(self) -> None:
        packet = {
            "portfolio_research": {
                "HELD": {
                    "facts": [fact()],
                    "assessment": assessment(),
                }
            },
            "opportunities": [],
        }
        sink = MemoryAlertSink()

        with StateStore(self.database) as store:
            PortfolioManagement(store).add("HELD", "1", "10")
            first = run_portfolio_research(store, self.provider(packet), sink)
            second = run_portfolio_research(store, self.provider(packet), sink)

            self.assertEqual("completed", first["status"])
            self.assertEqual(1, first["alerts_created"])
            self.assertEqual(0, second["alerts_created"])
            self.assertEqual(1, len(sink.sent))
            self.assertIn("facts", sink.sent[0])
            self.assertIn("analysis", sink.sent[0])
            self.assertEqual(1, store.count("facts"))
            self.assertEqual(1, store.count("reported_events"))

    def test_missing_holding_research_marks_run_partial(self) -> None:
        with StateStore(self.database) as store:
            PortfolioManagement(store).add("MISSING", "1", "10")
            result = run_portfolio_research(
                store,
                self.provider({"portfolio_research": {}, "opportunities": []}),
                MemoryAlertSink(),
            )
            self.assertEqual("partial", result["status"])
            self.assertEqual([], result["holdings_researched"])
            self.assertEqual(0, result["alerts_created"])

    def test_opportunities_exclude_owned_and_reject_weak_candidates(self) -> None:
        packet = {
            "portfolio_research": {},
            "opportunities": [
                {
                    "symbol": "OWNED",
                    "facts": [fact("Owned development")],
                    "assessment": assessment(action="BUY", event_id="owned"),
                },
                {
                    "symbol": "WEAK",
                    "facts": [fact("Weak development")],
                    "assessment": assessment(
                        action="WATCH",
                        meaningful=False,
                        event_id="weak",
                    ),
                },
                {
                    "symbol": "NEW",
                    "facts": [fact("New development")],
                    "assessment": assessment(action="BUY", event_id="new"),
                },
            ],
        }
        sink = MemoryAlertSink()

        with StateStore(self.database) as store:
            PortfolioManagement(store).add("OWNED", "1", "10")
            result = run_opportunity_research(
                store,
                self.provider(packet),
                sink,
            )
            self.assertEqual(["OWNED"], result["excluded_owned"])
            self.assertEqual(1, result["alerts_created"])
            self.assertEqual("NEW", sink.sent[0]["analysis"]["subject"])
            self.assertEqual(3, store.count("assessments"))

    def test_unsupported_meaningful_analysis_is_rejected(self) -> None:
        unsupported = assessment(action="BUY", event_id="unsupported")
        unsupported["supporting_fact_indexes"] = []
        packet = {
            "portfolio_research": {},
            "opportunities": [
                {
                    "symbol": "UNSUPPORTED",
                    "facts": [fact()],
                    "assessment": unsupported,
                }
            ],
        }

        with StateStore(self.database) as store:
            result = run_opportunity_research(
                store,
                self.provider(packet),
                MemoryAlertSink(),
            )
            self.assertEqual(0, result["alerts_created"])
            self.assertEqual("UNSUPPORTED", result["rejected"][0]["symbol"])
            self.assertEqual(0, store.count("alert_outbox"))


if __name__ == "__main__":
    unittest.main()
