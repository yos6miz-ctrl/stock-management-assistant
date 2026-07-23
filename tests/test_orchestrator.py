from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from investment_agent.models import RunStatus, SkillRunResult
from investment_agent.orchestrator import StockAgentOrchestrator
from investment_agent.storage import JsonStateStore


NOW = "2026-07-23T12:00:00+00:00"


class FakeSkill:
    def __init__(self, name: str, result: SkillRunResult | Exception):
        self.name = name
        self.result = result

    def run(self) -> SkillRunResult:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class RecordingNotifier:
    def __init__(self, error: Exception | None = None):
        self.messages = []
        self.error = error

    def send(self, changes):
        if self.error:
            raise self.error
        self.messages.append(changes)


def skill_result(
    name: str,
    output: dict,
    *,
    status: RunStatus = RunStatus.COMPLETE,
    revision: int = 1,
) -> SkillRunResult:
    return SkillRunResult(
        skill=name,
        status=status,
        portfolio_revision=revision,
        output=output,
        message="test",
        created_at=NOW,
    )


def candidate(symbol: str, rating: str) -> dict:
    return {
        "symbol": symbol,
        "rating": rating,
        "why_it_may_move": "A confirmed test catalyst could change expectations.",
        "why_it_may_be_mispriced": "Test expectations may be too low.",
        "entry_condition": "Wait for test confirmation.",
        "main_risk": "The test catalyst may fail.",
        "catalyst": {
            "event": "Test catalyst",
            "timing": "Q4 2026",
        },
    }


def recommendation(action: str, *, price: str = "100") -> tuple[SkillRunResult, ...]:
    return (
        skill_result(
            "portfolio_tracker",
            {"performance": {"current_value": price}},
        ),
        skill_result(
            "portfolio_analysis_and_recommendation",
            {
                "recommendations": [
                    {
                        "symbol": "AAA",
                        "action": action,
                        "why": f"Current test thesis supports {action}.",
                        "action_detail": f"Use the {action} test action.",
                        "main_risk": "Test execution risk.",
                        "future_catalyst": {
                            "event": "Test earnings",
                            "timing": "2026-10-15",
                        },
                    }
                ]
            },
        ),
        skill_result(
            "aggressive_short_term_opportunity_scanner",
            {"candidates": []},
        ),
    )


def with_opportunities(
    action: str,
    candidates: list[dict],
) -> tuple[SkillRunResult, ...]:
    items = list(recommendation(action))
    items[2] = skill_result(
        "aggressive_short_term_opportunity_scanner",
        {"candidates": candidates},
    )
    return tuple(items)


class OrchestratorTests(unittest.TestCase):
    def make_orchestrator(
        self,
        store: JsonStateStore,
        notifier: RecordingNotifier,
        results: tuple[SkillRunResult | Exception, ...],
    ) -> StockAgentOrchestrator:
        names = (
            "portfolio_tracker",
            "portfolio_analysis_and_recommendation",
            "aggressive_short_term_opportunity_scanner",
        )
        skills = [
            FakeSkill(name, result) for name, result in zip(names, results)
        ]
        return StockAgentOrchestrator(
            tracker=skills[0],
            portfolio_analysis=skills[1],
            opportunity_scanner=skills[2],
            store=store,
            notifier=notifier,
        )

    def test_first_successful_run_creates_baseline_without_email(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            notifier = RecordingNotifier()

            result = self.make_orchestrator(
                store, notifier, recommendation("hold")
            ).run()

            self.assertEqual("baseline_created", result.status)
            self.assertTrue(result.baseline_created)
            self.assertEqual([], notifier.messages)
            self.assertIsNotNone(store.get_last_valid_run())

    def test_no_changes_send_no_email(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            notifier = RecordingNotifier()
            self.make_orchestrator(
                store, notifier, recommendation("hold")
            ).run()

            result = self.make_orchestrator(
                store, notifier, recommendation("hold")
            ).run()

            self.assertEqual("complete_no_changes", result.status)
            self.assertEqual([], notifier.messages)

    def test_price_only_changes_send_no_email(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            notifier = RecordingNotifier()
            self.make_orchestrator(
                store, notifier, recommendation("hold", price="100")
            ).run()

            result = self.make_orchestrator(
                store, notifier, recommendation("hold", price="130")
            ).run()

            self.assertEqual("complete_no_changes", result.status)
            self.assertEqual([], notifier.messages)

    def test_portfolio_recommendation_change_sends_email(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            notifier = RecordingNotifier()
            self.make_orchestrator(
                store, notifier, recommendation("hold")
            ).run()

            result = self.make_orchestrator(
                store, notifier, recommendation("sell")
            ).run()

            self.assertTrue(result.email_sent)
            self.assertEqual(1, len(notifier.messages))
            change = notifier.messages[0][0]
            self.assertEqual("HOLD", change.previous_recommendation)
            self.assertEqual("SELL", change.new_recommendation)

    def test_new_aggressive_buy_sends_email_but_new_watch_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            notifier = RecordingNotifier()
            self.make_orchestrator(
                store,
                notifier,
                with_opportunities("hold", [candidate("NEW", "watch")]),
            ).run()

            result = self.make_orchestrator(
                store,
                notifier,
                with_opportunities(
                    "hold",
                    [
                        candidate("NEW", "aggressive_buy"),
                        candidate("WATCH", "watch"),
                    ],
                ),
            ).run()

            self.assertTrue(result.email_sent)
            self.assertEqual(1, len(result.material_changes))
            self.assertEqual("NEW", result.material_changes[0].symbol)
            self.assertEqual(
                "AGGRESSIVE_BUY",
                result.material_changes[0].new_recommendation,
            )

    def test_aggressive_buy_downgrade_and_removal_send_email(self) -> None:
        for current_candidates, expected in (
            ([candidate("NEW", "watch")], "WATCH"),
            ([], "REMOVED"),
        ):
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as directory:
                    store = JsonStateStore(Path(directory) / "state.json")
                    notifier = RecordingNotifier()
                    self.make_orchestrator(
                        store,
                        notifier,
                        with_opportunities(
                            "hold", [candidate("NEW", "aggressive_buy")]
                        ),
                    ).run()

                    result = self.make_orchestrator(
                        store,
                        notifier,
                        with_opportunities("hold", current_candidates),
                    ).run()

                    self.assertTrue(result.email_sent)
                    self.assertEqual(
                        expected,
                        result.material_changes[0].new_recommendation,
                    )

    def test_failed_and_incomplete_runs_do_not_replace_valid_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            notifier = RecordingNotifier()
            baseline_results = recommendation("hold")
            self.make_orchestrator(store, notifier, baseline_results).run()
            baseline = store.get_last_valid_run()

            failed = list(recommendation("sell"))
            failed[1] = RuntimeError("research failed")
            failed_result = self.make_orchestrator(
                store, notifier, tuple(failed)
            ).run()
            self.assertEqual("incomplete", failed_result.status)
            self.assertEqual(baseline, store.get_last_valid_run())

            incomplete = list(recommendation("sell"))
            incomplete[2] = skill_result(
                "aggressive_short_term_opportunity_scanner",
                {"candidates": []},
                status=RunStatus.PARTIAL,
            )
            incomplete_result = self.make_orchestrator(
                store, notifier, tuple(incomplete)
            ).run()
            self.assertEqual("incomplete", incomplete_result.status)
            self.assertEqual(baseline, store.get_last_valid_run())
            self.assertEqual([], notifier.messages)

    def test_duplicate_notification_is_prevented(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            notifier = RecordingNotifier()
            self.make_orchestrator(
                store, notifier, recommendation("hold")
            ).run()
            self.make_orchestrator(
                store, notifier, recommendation("sell")
            ).run()

            repeated = self.make_orchestrator(
                store, notifier, recommendation("sell")
            ).run()

            self.assertEqual("complete_no_changes", repeated.status)
            self.assertEqual(1, len(notifier.messages))
            self.assertEqual(1, len(store.notification_fingerprints()))

    def test_email_failure_preserves_previous_valid_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            self.make_orchestrator(
                store, RecordingNotifier(), recommendation("hold")
            ).run()
            baseline = store.get_last_valid_run()

            result = self.make_orchestrator(
                store,
                RecordingNotifier(RuntimeError("smtp unavailable")),
                recommendation("sell"),
            ).run()

            self.assertEqual("notification_failed", result.status)
            self.assertEqual(baseline, store.get_last_valid_run())


if __name__ == "__main__":
    unittest.main()
