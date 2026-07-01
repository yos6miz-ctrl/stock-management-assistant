# Codex Cloud setup

## Goal

Run this agent from Codex Cloud instead of the local desktop app.

## Recommended Codex Cloud settings

- Repository: this repository
- Environment setup script: none required
- Agent internet access: enabled
- Gmail connector: connect in Codex if you want email delivery
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

`Use this repository as the source of truth. Read AGENTS.md and all files under config/, then run one stock-monitor check as if it were a live scheduled run. If Gmail is available, send the result to yos6miz@gmail.com; otherwise return the exact email body in the response.`
