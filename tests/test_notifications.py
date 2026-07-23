from __future__ import annotations

import unittest

from investment_agent.notifications import MaterialChange, _render_email


class NotificationTests(unittest.TestCase):
    def test_email_contains_only_requested_change_fields(self) -> None:
        body = _render_email(
            (
                MaterialChange(
                    kind="Portfolio recommendation changed",
                    symbol="AAA",
                    previous_recommendation="HOLD",
                    new_recommendation="SELL",
                    reason="The test thesis changed.",
                    next_catalyst="Test earnings",
                    catalyst_timing="2026-10-15",
                    suggested_action="Review the position.",
                    main_risk="Test execution risk.",
                ),
            )
        )

        for label in (
            "Previous recommendation:",
            "New recommendation:",
            "Reason for the change:",
            "Next catalyst and expected date:",
            "Suggested action:",
            "Main risk:",
        ):
            self.assertIn(label, body)
        self.assertNotIn("Confidence", body)
        self.assertNotIn("Source", body)


if __name__ == "__main__":
    unittest.main()
