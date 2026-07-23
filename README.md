# Cloud Investment Agent

A small, provider-neutral foundation for a cloud investment research agent. It
has exactly three independently runnable skills:

1. **Portfolio management** stores holdings and an immutable change history.
2. **Portfolio research** evaluates every current holding and emits an alert
   only for a new, supported material development.
3. **Aggressive opportunity research** evaluates companies outside the
   portfolio and emits only supported, catalyst-backed opportunities.

The agent performs research support, portfolio tracking, recommendations, and
alerts. It does not place trades and has no brokerage integration.

## Architecture

All three skills share a persistent state store but do not call one another.
Portfolio management is the only writer of holdings. The two research skills
read a versioned portfolio snapshot and write sourced facts, analyses, run
records, and deduplicated alert events.

```text
cloud invoker
  +-- portfolio skill ---------------+
  +-- portfolio-research skill -------+-- persistent store
  +-- opportunities skill ------------+
              |
       research provider
              |
       alert outbox/sink
```

The current implementation deliberately does not select a market-data API,
news API, schedule, threshold, alert destination, cloud vendor, or portfolio.
`ResearchProvider` is the boundary for a future external-information adapter.
The included JSON provider makes the core testable without fabricating live
information.

## Requirements

- Python 3.11 or newer
- No runtime dependencies outside the Python standard library

## Install

```bash
python -m pip install -e .
```

## Portfolio management

```bash
investment-agent --db state/agent.db portfolio add \
  --symbol SYMBOL --quantity 10 --average-price 25.50 --notes "Research note"

investment-agent --db state/agent.db portfolio update \
  --symbol SYMBOL --quantity 12

investment-agent --db state/agent.db portfolio remove --symbol SYMBOL
investment-agent --db state/agent.db portfolio show
```

Quantities and average prices use decimal arithmetic. Basic calculations are
cost-basis calculations only; the core never invents a current market price.

## Research runs

Each research skill can run independently:

```bash
investment-agent --db state/agent.db portfolio-research --packet research.json
investment-agent --db state/agent.db opportunities --packet research.json
investment-agent --db state/agent.db alerts flush
```

The packet is supplied by a `ResearchProvider`. Its facts require source
provenance and confirmation state. Analyses reference those facts by their
zero-based indexes:

```json
{
  "portfolio_research": {
    "SYMBOL": {
      "facts": [
        {
          "category": "filing",
          "title": "Concise factual title",
          "detail": "Factual detail only",
          "event_time": "2026-01-01T00:00:00Z",
          "confirmation": "confirmed",
          "source": {
            "publisher": "Primary source",
            "url": "https://example.test/source",
            "retrieved_at": "2026-01-01T01:00:00Z"
          }
        }
      ],
      "assessment": {
        "action": "HOLD",
        "change_summary": "What materially changed",
        "why_it_matters": "Why the change affects the position",
        "catalyst": {
          "description": "Next known catalyst or explicitly unknown",
          "timing": "Expected timing or explicitly unknown"
        },
        "downside_risk": "Main downside risk",
        "confidence": "MEDIUM",
        "meaningful": true,
        "event_id": "stable-provider-event-id",
        "event_version": "material-version-1",
        "supporting_fact_indexes": [0]
      }
    }
  },
  "opportunities": []
}
```

An opportunity uses the same bundle shape and adds a top-level `symbol`.
Meaningful opportunity alerts require action `BUY`, a catalyst and timing,
downside risk, confidence, and at least one sourced supporting fact. Owned
symbols are excluded automatically.

`event_id` identifies the underlying development. `event_version` changes only
when a genuinely material update occurs. The pair prevents repeated alerts
while allowing a later material development to be reported.

## Cloud operation

The commands are one-shot processes suitable for a cloud job, container, or
serverless invocation. Point all invocations at the same durable database and
run them through a cloud-native invoker; a personal computer does not need to
remain online. Provider, scheduler, datastore service, secrets, and alert
delivery choices intentionally remain open.

## Test

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```
