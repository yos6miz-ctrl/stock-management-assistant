from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from .interfaces import RunnableSkill
from .models import RunStatus, SkillRunResult, utc_now
from .notifications import ChangeNotifier, MaterialChange
from .storage import JsonStateStore


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestratorResult:
    status: str
    baseline_created: bool
    email_sent: bool
    material_changes: tuple[MaterialChange, ...]
    skill_results: tuple[SkillRunResult, ...]
    errors: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "baseline_created": self.baseline_created,
            "email_sent": self.email_sent,
            "material_changes": [
                change.to_dict() for change in self.material_changes
            ],
            "skills": [item.to_dict() for item in self.skill_results],
            "errors": list(self.errors),
            "created_at": self.created_at,
        }


class StockAgentOrchestrator:
    """Run the three skills and notify only after a fully valid run."""

    def __init__(
        self,
        *,
        tracker: RunnableSkill,
        portfolio_analysis: RunnableSkill,
        opportunity_scanner: RunnableSkill,
        store: JsonStateStore,
        notifier: ChangeNotifier,
    ):
        self.skills = (tracker, portfolio_analysis, opportunity_scanner)
        self.store = store
        self.notifier = notifier

    def run(self) -> OrchestratorResult:
        completed: list[SkillRunResult] = []
        errors: list[str] = []
        for skill in self.skills:
            try:
                completed.append(skill.run())
            except Exception as exc:  # keep later independent skills runnable
                LOGGER.exception("%s failed", skill.name)
                errors.append(f"{skill.name}: {exc}")

        created_at = utc_now()
        if (
            errors
            or len(completed) != len(self.skills)
            or any(item.status != RunStatus.COMPLETE for item in completed)
            or len({item.portfolio_revision for item in completed}) != 1
        ):
            if not errors:
                errors.append(
                    "At least one skill was incomplete, unavailable, or used "
                    "a different portfolio revision."
                )
            return OrchestratorResult(
                status="incomplete",
                baseline_created=False,
                email_sent=False,
                material_changes=(),
                skill_results=tuple(completed),
                errors=tuple(errors),
                created_at=created_at,
            )

        current = build_valid_state(tuple(completed), created_at)
        previous = self.store.get_last_valid_run()
        if previous is None:
            self.store.commit_valid_run(current)
            return OrchestratorResult(
                status="baseline_created",
                baseline_created=True,
                email_sent=False,
                material_changes=(),
                skill_results=tuple(completed),
                errors=(),
                created_at=created_at,
            )

        changes = detect_material_changes(previous, current)
        if not changes:
            self.store.commit_valid_run(current)
            return OrchestratorResult(
                status="complete_no_changes",
                baseline_created=False,
                email_sent=False,
                material_changes=(),
                skill_results=tuple(completed),
                errors=(),
                created_at=created_at,
            )

        fingerprint = notification_fingerprint(previous, changes)
        if fingerprint in self.store.notification_fingerprints():
            self.store.commit_valid_run(current)
            return OrchestratorResult(
                status="complete_duplicate_suppressed",
                baseline_created=False,
                email_sent=False,
                material_changes=changes,
                skill_results=tuple(completed),
                errors=(),
                created_at=created_at,
            )

        try:
            self.notifier.send(changes)
        except Exception as exc:
            LOGGER.exception("Material-change email failed")
            return OrchestratorResult(
                status="notification_failed",
                baseline_created=False,
                email_sent=False,
                material_changes=changes,
                skill_results=tuple(completed),
                errors=(f"email: {exc}",),
                created_at=created_at,
            )

        self.store.commit_valid_run(
            current,
            notification={
                "fingerprint": fingerprint,
                "sent_at": utc_now(),
                "changes": [item.to_dict() for item in changes],
            },
        )
        return OrchestratorResult(
            status="complete_alert_sent",
            baseline_created=False,
            email_sent=True,
            material_changes=changes,
            skill_results=tuple(completed),
            errors=(),
            created_at=created_at,
        )


def build_valid_state(
    results: tuple[SkillRunResult, ...], created_at: str
) -> dict[str, Any]:
    by_skill = {item.skill: item for item in results}
    analysis = by_skill["portfolio_analysis_and_recommendation"]
    scanner = by_skill["aggressive_short_term_opportunity_scanner"]
    recommendations = {
        item["symbol"]: {
            "recommendation": str(item["action"]).upper(),
            "reason": item["why"],
            "next_catalyst": item["future_catalyst"]["event"],
            "catalyst_timing": item["future_catalyst"]["timing"],
            "suggested_action": item["action_detail"],
            "main_risk": item["main_risk"],
        }
        for item in analysis.output.get("recommendations", [])
    }
    opportunities = {
        item["symbol"]: {
            "recommendation": str(item["rating"]).upper(),
            "reason": (
                f"{item['why_it_may_move']} "
                f"{item['why_it_may_be_mispriced']}"
            ).strip(),
            "next_catalyst": item["catalyst"]["event"],
            "catalyst_timing": item["catalyst"]["timing"],
            "suggested_action": item["entry_condition"],
            "main_risk": item["main_risk"],
        }
        for item in scanner.output.get("candidates", [])
    }
    return {
        "created_at": created_at,
        "portfolio_revision": analysis.portfolio_revision,
        "portfolio_recommendations": recommendations,
        "opportunity_recommendations": opportunities,
    }


def detect_material_changes(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> tuple[MaterialChange, ...]:
    changes: list[MaterialChange] = []
    previous_portfolio = previous.get("portfolio_recommendations", {})
    current_portfolio = current.get("portfolio_recommendations", {})
    valid_portfolio_actions = {"BUY_MORE", "HOLD", "REDUCE", "SELL"}
    for symbol in sorted(set(previous_portfolio) & set(current_portfolio)):
        old = previous_portfolio[symbol]
        new = current_portfolio[symbol]
        old_action = old.get("recommendation")
        new_action = new.get("recommendation")
        if (
            old_action != new_action
            and old_action in valid_portfolio_actions
            and new_action in valid_portfolio_actions
        ):
            changes.append(
                _change(
                    kind="Portfolio recommendation changed",
                    symbol=symbol,
                    previous=old_action,
                    new=new_action,
                    details=new,
                )
            )

    previous_opportunities = previous.get("opportunity_recommendations", {})
    current_opportunities = current.get("opportunity_recommendations", {})
    opportunity_symbols = sorted(
        set(previous_opportunities) | set(current_opportunities)
    )
    for symbol in opportunity_symbols:
        old = previous_opportunities.get(symbol)
        new = current_opportunities.get(symbol)
        old_action = old.get("recommendation") if old else "NOT_LISTED"
        new_action = new.get("recommendation") if new else "REMOVED"
        if old_action != "AGGRESSIVE_BUY" and new_action == "AGGRESSIVE_BUY":
            changes.append(
                _change(
                    kind="New aggressive opportunity",
                    symbol=symbol,
                    previous=old_action,
                    new=new_action,
                    details=new,
                )
            )
        elif old_action == "AGGRESSIVE_BUY" and new_action != "AGGRESSIVE_BUY":
            details = new or {
                "reason": (
                    "The stock was not returned as a qualifying candidate in "
                    "the latest complete scan."
                ),
                "next_catalyst": old.get("next_catalyst", "Not available"),
                "catalyst_timing": old.get(
                    "catalyst_timing", "Not available"
                ),
                "suggested_action": (
                    "Do not initiate or add to the prior aggressive setup."
                ),
                "main_risk": old.get("main_risk", "Not available"),
            }
            changes.append(
                _change(
                    kind="Aggressive opportunity downgraded or removed",
                    symbol=symbol,
                    previous=old_action,
                    new=new_action,
                    details=details,
                )
            )
    return tuple(changes)


def notification_fingerprint(
    previous: dict[str, Any],
    changes: tuple[MaterialChange, ...],
) -> str:
    material = {
        "previous_valid_run": previous.get("created_at", ""),
        "changes": [
            {
                "kind": item.kind,
                "symbol": item.symbol,
                "previous": item.previous_recommendation,
                "new": item.new_recommendation,
            }
            for item in changes
        ],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _change(
    *,
    kind: str,
    symbol: str,
    previous: str,
    new: str,
    details: dict[str, Any],
) -> MaterialChange:
    return MaterialChange(
        kind=kind,
        symbol=symbol,
        previous_recommendation=previous,
        new_recommendation=new,
        reason=str(details["reason"]),
        next_catalyst=str(details["next_catalyst"]),
        catalyst_timing=str(details["catalyst_timing"]),
        suggested_action=str(details["suggested_action"]),
        main_risk=str(details["main_risk"]),
    )
