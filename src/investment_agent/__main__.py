from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any

from .config import AgentConfig, load_config
from .logging_config import configure_logging
from .notifications import GmailSmtpNotifier
from .orchestrator import StockAgentOrchestrator
from .models import Position
from .providers import OpenAIResearchProvider, PlaceholderExternalProvider
from .skills import (
    AggressiveShortTermOpportunityScannerSkill,
    PortfolioAnalysisAndRecommendationSkill,
    PortfolioTrackerSkill,
)
from .storage import JsonStateStore


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Investment agent")
    parser.add_argument(
        "--config",
        default="config/settings.json",
        help="path to the JSON configuration file",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    portfolio = commands.add_parser("portfolio", help="run Portfolio Tracker")
    portfolio_commands = portfolio.add_subparsers(
        dest="portfolio_command", required=True
    )

    add = portfolio_commands.add_parser("add")
    add.add_argument("--symbol", required=True)
    add.add_argument("--quantity", required=True)
    add.add_argument("--average-purchase-price", required=True)
    add.add_argument("--notes", default="")

    buy = portfolio_commands.add_parser("buy")
    buy.add_argument("--symbol", required=True)
    buy.add_argument("--quantity", required=True)
    buy.add_argument("--purchase-price", required=True)
    buy.add_argument("--notes")

    sell = portfolio_commands.add_parser("sell")
    sell.add_argument("--symbol", required=True)
    sell.add_argument("--quantity", required=True)

    correct = portfolio_commands.add_parser("correct")
    correct.add_argument("--symbol", required=True)
    correct.add_argument("--quantity")
    correct.add_argument("--average-purchase-price")
    correct.add_argument("--notes")

    remove = portfolio_commands.add_parser("remove")
    remove.add_argument("--symbol", required=True)

    portfolio_commands.add_parser("show")
    portfolio_commands.add_parser("track")
    portfolio_commands.add_parser("history")

    commands.add_parser(
        "portfolio-analysis",
        help="run Portfolio Analysis and Recommendation",
    )
    commands.add_parser(
        "opportunity-scan",
        help="run Aggressive Short-Term Opportunity Scanner",
    )
    commands.add_parser(
        "run-all",
        help="run all three skills and send material-change alerts",
    )
    commands.add_parser("state", help="show persisted JSON state")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        config = load_config(arguments.config)
        configure_logging(config.log_level)
        store = JsonStateStore(config.storage_path)
        output = dispatch(arguments, store, config)
        if isinstance(output, str):
            print(output)
        else:
            print(json.dumps(output, indent=2, sort_keys=True))
        if (
            isinstance(output, dict)
            and output.get("status") in {"incomplete", "notification_failed"}
        ):
            return 1
        return 0
    except Exception as exc:
        LOGGER.error("Command failed: %s", exc)
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2


def dispatch(
    arguments: argparse.Namespace,
    store: JsonStateStore,
    config: AgentConfig,
) -> str | dict[str, Any]:
    external_provider = PlaceholderExternalProvider()
    tracker = PortfolioTrackerSkill(
        store,
        external_provider,
        base_currency=config.base_currency,
    )

    if arguments.command == "portfolio":
        if arguments.portfolio_command == "add":
            return tracker.add_position(
                arguments.symbol,
                arguments.quantity,
                arguments.average_purchase_price,
                arguments.notes,
            ).to_dict()
        if arguments.portfolio_command == "buy":
            return tracker.record_buy(
                arguments.symbol,
                arguments.quantity,
                arguments.purchase_price,
                arguments.notes,
            ).to_dict()
        if arguments.portfolio_command == "sell":
            remaining = tracker.record_sell(
                arguments.symbol,
                arguments.quantity,
            )
            return {
                "status": "sale recorded",
                "symbol": arguments.symbol.upper(),
                "remaining_position": (
                    remaining.to_dict() if remaining is not None else None
                ),
            }
        if arguments.portfolio_command == "correct":
            return tracker.correct_position(
                arguments.symbol,
                quantity=arguments.quantity,
                average_purchase_price=arguments.average_purchase_price,
                notes=arguments.notes,
            ).to_dict()
        if arguments.portfolio_command == "remove":
            tracker.remove_position(arguments.symbol)
            return {
                "status": "removed",
                "symbol": arguments.symbol.upper(),
            }
        if arguments.portfolio_command == "show":
            return {
                "confirmed_portfolio": tracker.get_portfolio_snapshot().to_dict()
            }
        if arguments.portfolio_command == "track":
            tracker.market_data_provider = _provider(
                config.market_data_provider, config
            )
            return tracker.format_result(tracker.run())
        if arguments.portfolio_command == "history":
            return {"events": tracker.history()}

    if arguments.command == "portfolio-analysis":
        skill = PortfolioAnalysisAndRecommendationSkill(
            tracker,
            tracker,
            _provider(config.portfolio_analysis_provider, config),
            store,
        )
        return skill.format_result(skill.run())

    if arguments.command == "opportunity-scan":
        skill = AggressiveShortTermOpportunityScannerSkill(
            tracker,
            tracker,
            _provider(config.opportunity_research_provider, config),
            store,
        )
        return skill.format_result(skill.run())

    if arguments.command == "run-all":
        _sync_portfolio_from_environment(tracker)
        tracker.market_data_provider = _provider(
            config.market_data_provider, config
        )
        analysis = PortfolioAnalysisAndRecommendationSkill(
            tracker,
            tracker,
            _provider(config.portfolio_analysis_provider, config),
            store,
        )
        scanner = AggressiveShortTermOpportunityScannerSkill(
            tracker,
            tracker,
            _provider(config.opportunity_research_provider, config),
            store,
        )
        notifier = GmailSmtpNotifier(
            sender=os.environ.get("GMAIL_SENDER", ""),
            app_password=os.environ.get("GMAIL_APP_PASSWORD", ""),
            recipient=config.email_recipient,
        )
        result = StockAgentOrchestrator(
            tracker=tracker,
            portfolio_analysis=analysis,
            opportunity_scanner=scanner,
            store=store,
            notifier=notifier,
        ).run()
        return result.to_dict()

    if arguments.command == "state":
        return store.state_snapshot()
    raise ValueError("unsupported command")


def _provider(name: str, config: AgentConfig):
    if name == "placeholder":
        return PlaceholderExternalProvider()
    if name == "openai":
        return OpenAIResearchProvider(
            os.environ.get("OPENAI_API_KEY", ""),
            model=config.openai_model,
            reasoning_effort=config.openai_reasoning_effort,
        )
    raise ValueError(f"unsupported provider: {name}")


def _sync_portfolio_from_environment(tracker: PortfolioTrackerSkill) -> None:
    """Apply an optional exact portfolio supplied as an encrypted Actions secret."""
    raw = os.environ.get("PORTFOLIO_JSON")
    if raw is None or not raw.strip():
        return
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("PORTFOLIO_JSON must be a JSON array")

    desired: dict[str, Position] = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each PORTFOLIO_JSON item must be an object")
        position = Position.from_dict(item)
        if position.symbol in desired:
            raise ValueError(
                f"PORTFOLIO_JSON contains duplicate symbol {position.symbol}"
            )
        desired[position.symbol] = position

    current = {
        item.symbol: item for item in tracker.get_portfolio_snapshot().positions
    }
    for symbol in sorted(set(current) - set(desired)):
        tracker.remove_position(symbol)
    for symbol, wanted in sorted(desired.items()):
        existing = current.get(symbol)
        if existing is None:
            tracker.add_position(
                symbol,
                str(wanted.quantity),
                str(wanted.average_purchase_price),
                wanted.notes,
            )
        elif (
            existing.quantity != wanted.quantity
            or existing.average_purchase_price != wanted.average_purchase_price
            or existing.notes != wanted.notes
        ):
            tracker.correct_position(
                symbol,
                quantity=str(wanted.quantity),
                average_purchase_price=str(wanted.average_purchase_price),
                notes=wanted.notes,
            )


if __name__ == "__main__":
    raise SystemExit(main())
