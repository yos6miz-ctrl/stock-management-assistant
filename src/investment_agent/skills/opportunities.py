from __future__ import annotations

from typing import Any

from ..alerts import AlertSink, flush_pending_alerts
from ..models import ValidationError, normalize_symbol
from ..research import ResearchProvider, parse_bundle
from ..store import StateStore


def run_opportunity_research(
    store: StateStore,
    provider: ResearchProvider,
    sink: AlertSink,
) -> dict[str, Any]:
    """Skill 3: evaluate catalyst-backed opportunities outside the portfolio."""

    snapshot = store.portfolio_snapshot()
    owned = {position.symbol for position in snapshot.positions}
    run_id = store.start_run("opportunities", snapshot.revision)
    evaluated: list[str] = []
    excluded_owned: list[str] = []
    rejected: list[dict[str, str]] = []
    alerts_created = 0

    try:
        bundles = provider.opportunity_bundles()
        for bundle in bundles:
            raw_symbol = bundle.get("symbol")
            try:
                if not isinstance(raw_symbol, str):
                    raise ValidationError("opportunity symbol is required")
                symbol = normalize_symbol(raw_symbol)
                facts, assessment = parse_bundle(
                    symbol,
                    bundle,
                    skill="opportunities",
                )

                if symbol in owned:
                    store.record_assessment(
                        skill="opportunities",
                        facts=facts,
                        assessment=assessment,
                        portfolio_revision=snapshot.revision,
                        eligible=False,
                        rejection_reason="already owned",
                    )
                    excluded_owned.append(symbol)
                    continue

                eligible = assessment.action == "BUY" and assessment.meaningful
                rejection_reason = None
                if not eligible:
                    rejection_reason = "not a meaningful BUY opportunity"

                if store.record_assessment(
                    skill="opportunities",
                    facts=facts,
                    assessment=assessment,
                    portfolio_revision=snapshot.revision,
                    eligible=eligible,
                    rejection_reason=rejection_reason,
                ):
                    alerts_created += 1
                evaluated.append(symbol)
                if rejection_reason:
                    rejected.append({"symbol": symbol, "error": rejection_reason})
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append(
                    {
                        "symbol": raw_symbol if isinstance(raw_symbol, str) else "UNKNOWN",
                        "error": str(exc),
                    }
                )

        alerts_sent = flush_pending_alerts(store, sink)
        output: dict[str, Any] = {
            "run_id": run_id,
            "skill": "opportunities",
            "status": "completed",
            "portfolio_revision": snapshot.revision,
            "evaluated": evaluated,
            "excluded_owned": excluded_owned,
            "rejected": rejected,
            "alerts_created": alerts_created,
            "alerts_sent": alerts_sent,
        }
        store.finish_run(run_id, "completed", output)
        return output
    except Exception as exc:
        output = {
            "run_id": run_id,
            "skill": "opportunities",
            "status": "failed",
            "portfolio_revision": snapshot.revision,
        }
        store.finish_run(run_id, "failed", output, error=str(exc))
        raise
