from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from investment_agent.storage import JsonStateStore, StateStorageError


class JsonStateStoreTests(unittest.TestCase):
    def test_persists_buys_sells_and_corrections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "state.json"
            store = JsonStateStore(state_path)
            store.add_position("demo", "2", "10", "confirmed")

            after_buy = store.record_buy("DEMO", "2", "20")
            self.assertEqual("4", str(after_buy.quantity))
            self.assertEqual("15", str(after_buy.average_purchase_price))

            after_sell = store.record_sell("DEMO", "1")
            self.assertIsNotNone(after_sell)
            self.assertEqual("3", str(after_sell.quantity))
            self.assertEqual("15", str(after_sell.average_purchase_price))

            corrected = store.correct_position(
                "DEMO",
                quantity="4",
                average_purchase_price="14",
            )
            self.assertEqual("4", str(corrected.quantity))

            reopened = JsonStateStore(state_path)
            snapshot = reopened.get_portfolio_snapshot()
            self.assertEqual(4, snapshot.revision)
            self.assertEqual("14", str(snapshot.positions[0].average_purchase_price))
            self.assertEqual(
                ["add", "buy", "sell", "correct"],
                [event["action"] for event in reopened.portfolio_events()],
            )

    def test_full_sale_removes_only_the_instructed_position(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = JsonStateStore(Path(temporary_directory) / "state.json")
            store.add_position("ONE", "1", "10")
            store.add_position("TWO", "2", "20")

            remaining = store.record_sell("ONE", "1")

            self.assertIsNone(remaining)
            symbols = {
                position.symbol
                for position in store.get_portfolio_snapshot().positions
            }
            self.assertEqual({"TWO"}, symbols)

    def test_migrates_the_initial_skeleton_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "portfolio": {
                            "revision": 0,
                            "positions": [],
                            "events": [],
                        },
                        "skill_runs": [],
                        "reported_events": [],
                        "research_state": {},
                    }
                ),
                encoding="utf-8",
            )

            store = JsonStateStore(state_path)

            self.assertEqual(3, store.state_snapshot()["schema_version"])
            self.assertIn("performance_history", store.state_snapshot())
            self.assertIsNone(store.get_last_valid_run())

    def test_persists_last_valid_run_and_notification_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "state.json"
            store = JsonStateStore(state_path)
            baseline = {
                "created_at": "2026-07-23T00:00:00+00:00",
                "portfolio_recommendations": {},
                "opportunity_recommendations": {},
            }

            store.commit_valid_run(
                baseline,
                notification={
                    "fingerprint": "example-fingerprint",
                    "sent_at": "2026-07-23T00:00:01+00:00",
                    "changes": [],
                },
            )
            reopened = JsonStateStore(state_path)

            self.assertEqual(baseline, reopened.get_last_valid_run())
            self.assertEqual(
                frozenset({"example-fingerprint"}),
                reopened.notification_fingerprints(),
            )

    def test_rejects_corrupt_json_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "state.json"
            state_path.write_text("not json", encoding="utf-8")

            with self.assertRaises(StateStorageError):
                JsonStateStore(state_path)
