from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """Raised when the project configuration is invalid."""


@dataclass(frozen=True)
class AgentConfig:
    storage_path: Path
    log_level: str
    base_currency: str
    market_data_provider: str
    portfolio_analysis_provider: str
    opportunity_research_provider: str
    openai_model: str
    openai_reasoning_effort: str
    email_recipient: str


def load_config(config_path: str | Path) -> AgentConfig:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as config_file:
        raw: Any = json.load(config_file)

    if not isinstance(raw, dict):
        raise ConfigurationError("configuration must be a JSON object")

    storage_value = _required_text(raw, "storage_path")
    storage_path = Path(storage_value)
    if not storage_path.is_absolute():
        storage_path = (path.parent / storage_path).resolve()

    provider_fields = (
        "market_data_provider",
        "portfolio_analysis_provider",
        "opportunity_research_provider",
    )
    providers = {}
    for field in provider_fields:
        value = raw.get(field, "placeholder")
        if value not in {"placeholder", "openai"}:
            raise ConfigurationError(
                f"{field} must be either 'placeholder' or 'openai'"
            )
        providers[field] = value

    reasoning_effort = str(
        raw.get("openai_reasoning_effort", "medium")
    ).lower()
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
        raise ConfigurationError("openai_reasoning_effort is invalid")

    return AgentConfig(
        storage_path=storage_path,
        log_level=str(raw.get("log_level", "INFO")).upper(),
        base_currency=str(raw.get("base_currency", "USD")).upper(),
        market_data_provider=providers["market_data_provider"],
        portfolio_analysis_provider=providers["portfolio_analysis_provider"],
        opportunity_research_provider=providers[
            "opportunity_research_provider"
        ],
        openai_model=str(raw.get("openai_model", "gpt-5.6-sol")),
        openai_reasoning_effort=reasoning_effort,
        email_recipient=str(
            raw.get("email_recipient", "yos6miz@gmail.com")
        ),
    )


def _required_text(value: dict[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise ConfigurationError(f"{field} is required")
    return item.strip()
