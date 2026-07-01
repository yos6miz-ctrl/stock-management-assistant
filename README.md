# Stock Management Assistant

This repository is a GitHub snapshot of the Codex stock alert agent currently used from the local Codex app.

## What is included

- `automation.toml`: the live Codex automation definition copied from the local automation store
- `prompt.md`: the agent prompt extracted into plain text for easier editing
- `memory.md`: placeholder memory file for future tracked runs
- `work/`: placeholder project folder
- `outputs/`: placeholder runtime output folder

## Original local source

- Automation ID: `daily-aggressive-stock-portfolio-recommendations`
- Local automation store: `C:\Users\Popovtzer lab\.codex\automations\daily-aggressive-stock-portfolio-recommendations`
- The current local automation is thread-based rather than project-cwd-based, so the agent behavior is primarily defined by the automation prompt and Codex thread context.

## Notes

- This repo is meant to make the agent portable to GitHub-backed Codex workflows.
- The current local automation still runs from the Codex app until a cloud/project-backed replacement is created.
