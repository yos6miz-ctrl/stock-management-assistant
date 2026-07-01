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

Use this repository as the source of truth. Read `AGENTS.md` and all files under `config/`. Determine whether the current run is PRE-OPEN, MID, or CLOSE based on Israel time. Perform the required stock scan, then produce the short decisive alert exactly as specified in `config/delivery.md`. If Gmail is available, send the alert to `yos6miz@gmail.com` and also include the same result in the run output. If no real catalyst-backed action exists, say so clearly and do not pad the output.
