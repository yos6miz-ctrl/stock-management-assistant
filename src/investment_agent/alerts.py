from __future__ import annotations

import json
from typing import Any, Protocol

from .store import StateStore


class AlertSink(Protocol):
    def send(self, payload: dict[str, Any]) -> None:
        ...


class StdoutAlertSink:
    def send(self, payload: dict[str, Any]) -> None:
        print(json.dumps(payload, indent=2, sort_keys=True))


class MemoryAlertSink:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


def flush_pending_alerts(store: StateStore, sink: AlertSink) -> int:
    sent = 0
    for alert in store.pending_alerts():
        sink.send(alert["payload"])
        store.mark_alert_sent(alert["id"])
        sent += 1
    return sent
