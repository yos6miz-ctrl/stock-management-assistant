from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investment_agent.__main__ import _sync_portfolio_from_environment
from investment_agent.providers import PlaceholderExternalProvider
from investment_agent.skills import PortfolioTrackerSkill
from investment_agent.storage import JsonStateStore


class PortfolioEnvironmentSyncTests(unittest.TestCase):
    def test_portfolio_secret_is_an_exact_user_confirmed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStateStore(Path(directory) / "state.json")
            tracker = PortfolioTrackerSkill(
                store,
                PlaceholderExternalProvider(),
            )
            tracker.add_position("OLD", "1", "5")
            payload = json.dumps(
                [
                    {
                        "symbol": "NEW",
                        "quantity": "2",
                        "average_purchase_price": "10.50",
                        "notes": "confirmed test data",
                    }
                ]
            )

            with patch.dict("os.environ", {"PORTFOLIO_JSON": payload}):
                _sync_portfolio_from_environment(tracker)
                revision_after_first_sync = (
                    tracker.get_portfolio_snapshot().revision
                )
                _sync_portfolio_from_environment(tracker)

            snapshot = tracker.get_portfolio_snapshot()
            self.assertEqual(["NEW"], [item.symbol for item in snapshot.positions])
            self.assertEqual("2", str(snapshot.positions[0].quantity))
            self.assertEqual(revision_after_first_sync, snapshot.revision)


if __name__ == "__main__":
    unittest.main()
