# Codex Cloud setup

## Goal

Run this agent from Codex Cloud instead of the local desktop app.

## Recommended Codex Cloud settings

- Repository: this repository
- Environment setup script: none required
- Agent internet access: enabled
- Phone notifications: enable Codex / ChatGPT app notifications on the phone
- Gmail connector: optional only if it becomes available in Codex Cloud; current verified delivery path is Codex output / inbox
- Timezone: verify the automation is created for Israel time

## How to use this repo

When starting a cloud task, instruct Codex to:

1. read `AGENTS.md`
2. read `config/portfolio.md`
3. read `config/alert-policy.md`
4. read `config/delivery.md`
5. run the stock scan and produce the short decisive output

## Suggested first cloud test

Prompt:

`Use this repository as the source of truth. Read AGENTS.md and all files under config/, then run one stock-monitor check as if it were a live scheduled run. Return the exact phone-notification-ready alert in the run output. Do not require Gmail.`
