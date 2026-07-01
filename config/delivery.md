# Delivery rules

- Primary delivery: Codex Cloud run output / Codex inbox for phone notification
- Email target, if a Gmail plugin is available in a future thread: `yos6miz@gmail.com`
- The run output is mandatory on every scheduled run
- Format the first line so it works as a phone notification headline
- Do not fail the cloud run just because Gmail is unavailable

## Visible output format

- Maximum `12` short lines
- First line must be exactly one bold action line beginning with one of:
  - `**URGENT SELL:**`
  - `**URGENT BUY:**`
  - `**BUY:**`
  - `**SELL:**`
  - `**KEEP:**`
  - `**NO ACTION:**`
- Then list only important holding actions
- Then include `Aggressive ideas:` with `0-3` tickers
- End with `Sources:` and `3-6` links
- No long tables
- No long explanations
- Use decisive labels such as `BUY`, `SELL`, `KEEP`, `WATCH`, `AVOID`, `NONE`, or `URGENT`
