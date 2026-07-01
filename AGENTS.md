## Repository purpose

This repository defines a recurring research-and-alert agent, not an application codebase.

## Run defaults

- Treat `config/portfolio.md`, `config/alert-policy.md`, and `config/delivery.md` as the source of truth.
- Use `prompt.md` only as the legacy full prompt when you need the exact older wording.
- Assume the user's working timezone is `Asia/Jerusalem` unless the active task says otherwise.
- Keep visible outputs short and decisive.
- Prefer primary or near-primary sources over market chatter.
- Do not depend on hidden local files, local Codex thread memory, or laptop-only state.

## Cloud-task expectations

- Internet access is required for routine runs.
- Gmail delivery is mandatory for scheduled stock-alert runs.
- Use the Gmail plugin explicitly for email delivery whenever it is available in the thread.
- If Gmail is unavailable, do not silently continue. Return a clear failure line that says `GMAIL NOT AVAILABLE - email was not sent`.
- If no real catalyst-backed action exists, say so clearly rather than padding results.

## Validation

- Validate by checking that the final alert obeys the formatting rules in `config/delivery.md`.
- Do not invent sources or prices.
