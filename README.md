# Stock Management Assistant

This repository is the GitHub-backed version of the user's Codex stock monitoring agent.

It is structured so Codex Cloud can run from repository files rather than relying on hidden local thread context from one laptop.

## Repository layout

- `AGENTS.md`: repo-level instructions Codex should load automatically
- `config/portfolio.md`: current holdings and user preferences
- `config/alert-policy.md`: research and decision rules
- `config/delivery.md`: output and delivery requirements
- `docs/cloud-setup.md`: how to configure this repo in Codex Cloud
- `docs/automation-spec.md`: schedule and paste-ready automation prompt
- `prompt.md`: legacy full prompt copied from the local automation
- `automation.toml`: snapshot of the local Codex automation definition
- `memory.md`: repo-local memory placeholder for future cloud usage

## Current status

This repository is now suitable as a source repo for Codex Cloud tasks, but the cloud automation still needs to be created in the Codex web UI.

## Important note

The live local automation was thread-based, not project-cwd-based. Because of that, this repo makes the previously implicit context explicit in versioned files under `config/` and `docs/`.
