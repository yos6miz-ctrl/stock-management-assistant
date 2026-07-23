# Stock Management Assistant

A cloud-run Python agent with three independently runnable skills:

1. Portfolio Tracker
2. Portfolio Analysis and Recommendation
3. Aggressive Short-Term Opportunity Scanner

The agent tracks user-confirmed holdings, researches current information through
the OpenAI Responses API with web search, produces strict structured outputs,
and emails only material recommendation changes. It does not connect to a
brokerage or execute trades.

## Architecture

```text
GitHub Actions (only scheduler)
             |
             v
      StockAgentOrchestrator
             |
     1. Portfolio Tracker ---------- OpenAI current-price research
     2. Portfolio Analysis --------- OpenAI holding research
     3. Opportunity Scanner -------- OpenAI broad-market research
             |
             v
       Material change detector
        |                  |
   no changes          material changes
        |                  |
   save baseline       Gmail alert, then save baseline
             \             /
              JSON state cache
```

Each skill remains directly runnable. The orchestrator calls them in dependency
order and accepts a run as valid only when all three complete against the same
portfolio revision.

The shared models keep sourced facts, management claims, estimates, rumors,
conclusions, catalysts, and recommendations as separate structured fields.
Provider output is rejected when required holdings, evidence, sources, catalyst
timing, entry/exit logic, or risk controls are incomplete.

## Material-change alerts

The last successful valid run is the sole comparison baseline. Email is sent
only for:

- a holding recommendation changing between `BUY_MORE`, `HOLD`, `REDUCE`, and
  `SELL`;
- a candidate newly becoming `AGGRESSIVE_BUY`;
- an existing `AGGRESSIVE_BUY` becoming `WATCH`, `AVOID`, removed, or otherwise
  invalidated.

Price and profit/loss changes, explanation wording, candidate rank, new
`WATCH` candidates, and confidence-only changes do not trigger email.

The first successful run creates a baseline without sending email. Failed or
incomplete research never replaces the last valid baseline. If an email fails,
the old baseline is retained so the change can be retried. A notification
fingerprint prevents normal duplicate delivery.

## Cloud execution

`.github/workflows/stock-agent.yml`:

- is the only scheduler;
- uses the requested `Asia/Jerusalem` timezone;
- prevents overlapping runs;
- restores the last successful JSON state from the GitHub Actions cache;
- runs every unit test before live research;
- runs the three-skill orchestrator;
- saves state only after a successful run.

The checked-in cron expression is the exact requested
`17 0,6,12,18 * * *`. In standard cron field order, it runs at 00:17, 06:17,
12:17, and 18:17 Israel time. If the intended times are instead 05:00, 11:00,
17:00, and 23:00, change it to `0 5,11,17,23 * * *`.

No user computer is involved after the GitHub setup.

## GitHub secrets

Add these required Actions secrets under repository **Settings → Secrets and
variables → Actions**:

- `OPENAI_API_KEY`
- `GMAIL_SENDER`
- `GMAIL_APP_PASSWORD`

`GMAIL_SENDER` must be the Gmail account associated with the app password.
Alerts are sent only to `yos6miz@gmail.com`.

An optional encrypted `PORTFOLIO_JSON` secret lets the cloud workflow maintain
the exact confirmed portfolio without committing private holdings to the
repository. Its value is a JSON array:

```json
[
  {
    "symbol": "EXAMPLE",
    "quantity": "2",
    "average_purchase_price": "10.50",
    "notes": "Optional confirmed note"
  }
]
```

When present, this is treated as the user-approved complete portfolio: changed
values are corrected, new symbols are added, and omitted symbols are removed.
Malformed input fails the run before a new valid baseline can be saved. The
repository contains no real holdings.

## Configuration

`config/settings.json` selects:

- JSON state path and logging level;
- base portfolio currency;
- OpenAI for market data, portfolio research, and opportunity research;
- model `gpt-5.6-sol` with medium reasoning effort;
- the fixed email recipient.

Credentials are read only from environment variables. The standard-library
OpenAI adapter calls `POST /v1/responses`, enables web search on every research
request, and requests strict JSON-schema output. The offline placeholder
provider remains available for development.

## Local commands

Requirements: Python 3.11 or newer. The runtime has no third-party Python
dependencies.

```bash
python -m pip install -e .
```

Manage confirmed positions:

```bash
investment-agent portfolio add \
  --symbol EXAMPLE --quantity 2 --average-purchase-price 10.50
investment-agent portfolio buy \
  --symbol EXAMPLE --quantity 1 --purchase-price 12.00
investment-agent portfolio sell --symbol EXAMPLE --quantity 1
investment-agent portfolio correct \
  --symbol EXAMPLE --average-purchase-price 10.75
investment-agent portfolio remove --symbol EXAMPLE
investment-agent portfolio show
investment-agent portfolio history
```

Run each skill independently:

```bash
investment-agent portfolio track
investment-agent portfolio-analysis
investment-agent opportunity-scan
```

Run the cloud sequence locally, with required environment variables configured:

```bash
investment-agent run-all
```

Inspect local persisted state:

```bash
investment-agent state
```

## Persistence

`JsonStateStore` performs atomic file replacement and stores:

- confirmed positions and their mutation history;
- performance history;
- structured portfolio recommendation history;
- structured opportunity-scan history;
- independent skill-run records;
- the last complete valid comparison state;
- notification fingerprints.

Runtime state and credentials are ignored by Git. In GitHub Actions, a new cache
is saved only when tests, research, notification handling, and orchestration all
succeed.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The deterministic test suite covers portfolio calculations and validation,
first-run baselining, no-change and price-only runs, recommendation transitions,
new and downgraded/removed aggressive opportunities, failed/incomplete run
protection, duplicate suppression, email content, JSON migrations, and OpenAI
structured-output request/response mapping. Tests never call live APIs.
