# Repository operating rules

This repository contains a provider-neutral, cloud-ready investment research
agent with exactly three user-facing skills:

1. portfolio management;
2. portfolio research and recommendations;
3. aggressive opportunity research.

Keep the skills independently runnable. Shared storage, research-provider, and
alert interfaces are infrastructure rather than additional skills.

## Safety and data integrity

- Never place trades or connect to brokerage accounts.
- Never invent facts, prices, catalysts, sources, or recommendations.
- Keep sourced facts separate from analysis.
- Mark unconfirmed or conflicting information explicitly.
- Do not emit unsupported or duplicate alerts.
- Preserve state and portfolio history between runs.
- Do not commit real holdings, credentials, API keys, alert destinations,
  schedules, or deployment-specific configuration.

## Development

- Keep the core provider-neutral until a provider is explicitly selected.
- Prefer Python standard-library dependencies in the core.
- Run `python -m unittest discover -s tests -v` with `PYTHONPATH=src` before
  publishing changes.
