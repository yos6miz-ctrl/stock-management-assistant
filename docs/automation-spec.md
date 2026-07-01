# Cloud automation spec

## Schedule

Weekdays, Israel time:

- `15:45`
- `19:45`
- `22:45`

Equivalent cron expression:

`45 15,19,22 * * 1-5`

Confirm the Codex automation timezone before saving.

## Paste-ready automation prompt

Use this repository as the source of truth. Read `AGENTS.md` and all files under `config/`. Determine whether the current run is PRE-OPEN, MID, or CLOSE based on Israel time. Perform the required stock scan, then produce the short decisive alert exactly as specified in `config/delivery.md`. Primary delivery is the Codex Cloud run output / Codex inbox so it can appear on the phone app. Make the first line a concise phone-notification headline. Do not require Gmail, because Gmail is not available in the current Codex Cloud thread setup. If no real catalyst-backed action exists, still post the stock alert and say so clearly without padding the output.
