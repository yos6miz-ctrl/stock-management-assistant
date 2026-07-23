from __future__ import annotations

import argparse
import json
import os
from typing import Any

from .alerts import StdoutAlertSink, flush_pending_alerts
from .research import JsonResearchProvider
from .skills import (
    PortfolioManagement,
    run_opportunity_research,
    run_portfolio_research,
)
from .store import StateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cloud investment agent")
    parser.add_argument(
        "--db",
        default=os.environ.get("INVESTMENT_AGENT_DB", "state/investment-agent.db"),
        help="path to the persistent state database",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    portfolio = commands.add_parser("portfolio", help="run portfolio management")
    portfolio_commands = portfolio.add_subparsers(
        dest="portfolio_command", required=True
    )

    add = portfolio_commands.add_parser("add")
    add.add_argument("--symbol", required=True)
    add.add_argument("--quantity", required=True)
    add.add_argument("--average-price", required=True)
    add.add_argument("--notes", default="")

    update = portfolio_commands.add_parser("update")
    update.add_argument("--symbol", required=True)
    update.add_argument("--quantity")
    update.add_argument("--average-price")
    update.add_argument("--notes")

    remove = portfolio_commands.add_parser("remove")
    remove.add_argument("--symbol", required=True)

    portfolio_commands.add_parser("show")
    portfolio_commands.add_parser("history")

    holding_research = commands.add_parser("portfolio-research")
    holding_research.add_argument("--packet", required=True)

    opportunities = commands.add_parser("opportunities")
    opportunities.add_argument("--packet", required=True)

    alerts = commands.add_parser("alerts")
    alert_commands = alerts.add_subparsers(dest="alert_command", required=True)
    alert_commands.add_parser("flush")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    sink = StdoutAlertSink()

    try:
        with StateStore(arguments.db) as store:
            result = dispatch(arguments, store, sink)
            if result is not None:
                print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2


def dispatch(
    arguments: argparse.Namespace,
    store: StateStore,
    sink: StdoutAlertSink,
) -> dict[str, Any] | None:
    if arguments.command == "portfolio":
        skill = PortfolioManagement(store)
        if arguments.portfolio_command == "add":
            return skill.add(
                arguments.symbol,
                arguments.quantity,
                arguments.average_price,
                arguments.notes,
            ).as_dict()
        if arguments.portfolio_command == "update":
            return skill.update(
                arguments.symbol,
                quantity=arguments.quantity,
                average_price=arguments.average_price,
                notes=arguments.notes,
            ).as_dict()
        if arguments.portfolio_command == "remove":
            skill.remove(arguments.symbol)
            return {"status": "removed", "symbol": arguments.symbol.upper()}
        if arguments.portfolio_command == "show":
            return skill.current()
        if arguments.portfolio_command == "history":
            return {"events": skill.history()}

    if arguments.command == "portfolio-research":
        return run_portfolio_research(
            store,
            JsonResearchProvider(arguments.packet),
            sink,
        )

    if arguments.command == "opportunities":
        return run_opportunity_research(
            store,
            JsonResearchProvider(arguments.packet),
            sink,
        )

    if arguments.command == "alerts" and arguments.alert_command == "flush":
        return {"alerts_sent": flush_pending_alerts(store, sink)}

    raise ValueError("unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
