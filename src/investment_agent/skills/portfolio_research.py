from __future__ import annotations

from typing import Any

from ..alerts import AlertSink, flush_pending_alerts
from ..models import ValidationError
from ..research import ResearchProvider, parse_bundle
from ..store import StateStore


def run_portfolio_research(
    store: StateStore,
    provider: ResearchProvider,
    sink: AlertSink,
) -> dict[str, Any]:
    """Skill 2: evaluate every current holding using provider-supplied facts."""

    snapshot = store.portfolio_snapshot()
    run_id = store.start_run("portfolio_research", snapshot.revision)
    researched: list[str] = []
    errors: list[dict[str, str]] = []
    alerts_created = 0

    try:
        for position in snapshot.positions:
            try:
                bundle = provider.holding_bundle(position.symbol)
                if bundle is None:
                    raise ValidationError("no current research bundle was supplied")
                facts, assessment = parse_bundle(
                    position.symbol,
                    bundle,
                    skill="portfolio_research",
                )
                if store.record_assessment(
                    skill="portfolio_research",
                    facts=facts,
                    assessment=assessment,
                    portfolio_revision=snapshot.revision,
                    eligible=True,
                ):
                    alerts_created += 1
                researched.append(position.symbol)
            except (KeyError, TypeError, ValueError) as exc:
                errors.append({"symbol": position.symbol, "error": str(exc)})

        alerts_sent = flush_pending_alerts(store, sink)
        status = "completed" if not errors else "partial"
        output: dict[str, Any] = {
            "run_id": run_id,
            "skill": "portfolio_research",
            "status": status,
            "portfolio_revision": snapshot.revision,
            "holdings_expected": len(snapshot.positions),
            "holdings_researched": researched,
            "errors": errors,
            "alerts_created": alerts_created,
            "alerts_sent": alerts_sent,
        }
        store.finish_run(run_id, status, output)
        return output
    except Exception as exc:
        output = {
            "run_id": run_id,
            "skill": "portfolio_research",
            "status": "failed",
            "portfolio_revision": snapshot.revision,
        }
        store.finish_run(run_id, "failed", output, error=str(exc))
        raise
