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
- Primary delivery for Codex Cloud is the run output / Codex inbox, which should surface through the Codex or ChatGPT phone app.
- Gmail is not available in the current Codex Cloud thread setup. Do not treat Gmail as required for cloud runs.
- If a Gmail plugin is available in a future thread, it may be used as a secondary delivery path, but the cloud run must still produce the phone-notification-ready output.
- If no real catalyst-backed action exists, say so clearly rather than padding results.

## Validation

- Validate by checking that the final alert obeys the formatting rules in `config/delivery.md`.
- Do not invent sources or prices.
