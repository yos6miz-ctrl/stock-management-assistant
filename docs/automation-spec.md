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

Use this repository as the source of truth. Read `AGENTS.md` and all files under `config/`. Determine whether the current run is PRE-OPEN, MID, or CLOSE based on Israel time. Perform the required stock scan, then produce the short decisive alert exactly as specified in `config/delivery.md`. Use the Gmail plugin explicitly to send the email to `yos6miz@gmail.com`; sending the email is mandatory on every run. Also include the exact same result in the run output. If Gmail is unavailable, do not silently skip email: return `GMAIL NOT AVAILABLE - email was not sent` and explain the blocker briefly. If no real catalyst-backed action exists, still send the email and say so clearly without padding the output.
