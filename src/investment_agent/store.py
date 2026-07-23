from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from .models import (
    Assessment,
    PortfolioSnapshot,
    Position,
    SourceFact,
    decimal_text,
    normalize_symbol,
    positive_decimal,
    utc_now,
)


class StateStore:
    """SQLite-backed persistent state shared by the three independent skills."""

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO metadata(key, value)
            VALUES ('portfolio_revision', '0');

            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                quantity TEXT NOT NULL,
                average_price TEXT NOT NULL,
                notes TEXT NOT NULL,
                active INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS portfolio_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                revision INTEGER NOT NULL,
                action TEXT NOT NULL,
                symbol TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facts (
                fact_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                event_time TEXT NOT NULL,
                confirmation TEXT NOT NULL,
                publisher TEXT NOT NULL,
                source_url TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill TEXT NOT NULL,
                subject TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_version TEXT NOT NULL,
                action TEXT NOT NULL,
                change_summary TEXT NOT NULL,
                why_it_matters TEXT NOT NULL,
                catalyst TEXT NOT NULL,
                catalyst_timing TEXT NOT NULL,
                downside_risk TEXT NOT NULL,
                confidence TEXT NOT NULL,
                meaningful INTEGER NOT NULL,
                supporting_fact_ids_json TEXT NOT NULL,
                portfolio_revision INTEGER NOT NULL,
                eligible INTEGER NOT NULL,
                rejection_reason TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(skill, event_id, event_version)
            );

            CREATE TABLE IF NOT EXISTS reported_events (
                skill TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_version TEXT NOT NULL,
                first_reported_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(skill, event_id, event_version)
            );

            CREATE TABLE IF NOT EXISTS alert_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                UNIQUE(skill, event_id, event_version)
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                portfolio_revision INTEGER NOT NULL,
                error TEXT,
                output_json TEXT
            );
            """
        )
        self.connection.commit()

    def _revision(self, connection: sqlite3.Connection | None = None) -> int:
        target = connection or self.connection
        row = target.execute(
            "SELECT value FROM metadata WHERE key = 'portfolio_revision'"
        ).fetchone()
        return int(row["value"])

    def _next_revision(self, connection: sqlite3.Connection) -> int:
        revision = self._revision(connection) + 1
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'portfolio_revision'",
            (str(revision),),
        )
        return revision

    @staticmethod
    def _position_from_row(row: sqlite3.Row) -> Position:
        return Position(
            symbol=row["symbol"],
            quantity=Decimal(row["quantity"]),
            average_price=Decimal(row["average_price"]),
            notes=row["notes"],
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_position(
        self,
        symbol: str,
        quantity: str | int | float | Decimal,
        average_price: str | int | float | Decimal,
        notes: str = "",
    ) -> Position:
        normalized = normalize_symbol(symbol)
        parsed_quantity = positive_decimal(quantity, "quantity")
        parsed_average = positive_decimal(average_price, "average_price")
        now = utc_now()

        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM positions WHERE symbol = ?", (normalized,)
            ).fetchone()
            if existing is not None and existing["active"]:
                raise ValueError(f"position {normalized} already exists")

            revision = self._next_revision(connection)
            before = (
                json.dumps(self._position_from_row(existing).as_dict(), sort_keys=True)
                if existing is not None
                else None
            )
            created_at = existing["created_at"] if existing is not None else now
            connection.execute(
                """
                INSERT INTO positions(
                    symbol, quantity, average_price, notes, active,
                    revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    quantity = excluded.quantity,
                    average_price = excluded.average_price,
                    notes = excluded.notes,
                    active = 1,
                    revision = excluded.revision,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized,
                    decimal_text(parsed_quantity),
                    decimal_text(parsed_average),
                    notes,
                    revision,
                    created_at,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM positions WHERE symbol = ?", (normalized,)
            ).fetchone()
            position = self._position_from_row(row)
            connection.execute(
                """
                INSERT INTO portfolio_events(
                    revision, action, symbol, before_json, after_json, created_at
                ) VALUES (?, 'add', ?, ?, ?, ?)
                """,
                (
                    revision,
                    normalized,
                    before,
                    json.dumps(position.as_dict(), sort_keys=True),
                    now,
                ),
            )
        return position

    def update_position(
        self,
        symbol: str,
        *,
        quantity: str | int | float | Decimal | None = None,
        average_price: str | int | float | Decimal | None = None,
        notes: str | None = None,
    ) -> Position:
        normalized = normalize_symbol(symbol)
        if quantity is None and average_price is None and notes is None:
            raise ValueError("at least one field must be updated")

        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM positions WHERE symbol = ? AND active = 1",
                (normalized,),
            ).fetchone()
            if row is None:
                raise KeyError(f"active position {normalized} was not found")

            before_position = self._position_from_row(row)
            new_quantity = (
                positive_decimal(quantity, "quantity")
                if quantity is not None
                else before_position.quantity
            )
            new_average = (
                positive_decimal(average_price, "average_price")
                if average_price is not None
                else before_position.average_price
            )
            new_notes = notes if notes is not None else before_position.notes
            revision = self._next_revision(connection)
            now = utc_now()
            connection.execute(
                """
                UPDATE positions
                SET quantity = ?, average_price = ?, notes = ?,
                    revision = ?, updated_at = ?
                WHERE symbol = ?
                """,
                (
                    decimal_text(new_quantity),
                    decimal_text(new_average),
                    new_notes,
                    revision,
                    now,
                    normalized,
                ),
            )
            updated_row = connection.execute(
                "SELECT * FROM positions WHERE symbol = ?", (normalized,)
            ).fetchone()
            position = self._position_from_row(updated_row)
            connection.execute(
                """
                INSERT INTO portfolio_events(
                    revision, action, symbol, before_json, after_json, created_at
                ) VALUES (?, 'update', ?, ?, ?, ?)
                """,
                (
                    revision,
                    normalized,
                    json.dumps(before_position.as_dict(), sort_keys=True),
                    json.dumps(position.as_dict(), sort_keys=True),
                    now,
                ),
            )
        return position

    def remove_position(self, symbol: str) -> None:
        normalized = normalize_symbol(symbol)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM positions WHERE symbol = ? AND active = 1",
                (normalized,),
            ).fetchone()
            if row is None:
                raise KeyError(f"active position {normalized} was not found")

            before_position = self._position_from_row(row)
            revision = self._next_revision(connection)
            now = utc_now()
            connection.execute(
                """
                UPDATE positions
                SET active = 0, revision = ?, updated_at = ?
                WHERE symbol = ?
                """,
                (revision, now, normalized),
            )
            connection.execute(
                """
                INSERT INTO portfolio_events(
                    revision, action, symbol, before_json, after_json, created_at
                ) VALUES (?, 'remove', ?, ?, NULL, ?)
                """,
                (
                    revision,
                    normalized,
                    json.dumps(before_position.as_dict(), sort_keys=True),
                    now,
                ),
            )

    def portfolio_snapshot(self) -> PortfolioSnapshot:
        rows = self.connection.execute(
            "SELECT * FROM positions WHERE active = 1 ORDER BY symbol"
        ).fetchall()
        return PortfolioSnapshot(
            revision=self._revision(),
            positions=tuple(self._position_from_row(row) for row in rows),
        )

    def portfolio_history(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM portfolio_events ORDER BY revision"
        ).fetchall()
        return [dict(row) for row in rows]

    def start_run(self, skill: str, portfolio_revision: int) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO runs(skill, started_at, status, portfolio_revision)
            VALUES (?, ?, 'running', ?)
            """,
            (skill, utc_now(), portfolio_revision),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        output: dict[str, Any],
        error: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE runs
            SET completed_at = ?, status = ?, error = ?, output_json = ?
            WHERE id = ?
            """,
            (utc_now(), status, error, json.dumps(output, sort_keys=True), run_id),
        )
        self.connection.commit()

    def record_assessment(
        self,
        *,
        skill: str,
        facts: tuple[SourceFact, ...],
        assessment: Assessment,
        portfolio_revision: int,
        eligible: bool,
        rejection_reason: str | None = None,
    ) -> bool:
        """Store facts/analysis and enqueue a new alert atomically.

        Returns True only when a new outbox record is created.
        """

        now = utc_now()
        with self.transaction() as connection:
            for fact in facts:
                connection.execute(
                    """
                    INSERT INTO facts(
                        fact_id, subject, category, title, detail, event_time,
                        confirmation, publisher, source_url, retrieved_at,
                        first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fact_id) DO UPDATE SET
                        confirmation = excluded.confirmation,
                        retrieved_at = excluded.retrieved_at,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        fact.fact_id,
                        fact.subject,
                        fact.category,
                        fact.title,
                        fact.detail,
                        fact.event_time,
                        fact.confirmation,
                        fact.publisher,
                        fact.source_url,
                        fact.retrieved_at,
                        now,
                        now,
                    ),
                )

            connection.execute(
                """
                INSERT OR IGNORE INTO assessments(
                    skill, subject, event_id, event_version, action,
                    change_summary, why_it_matters, catalyst, catalyst_timing,
                    downside_risk, confidence, meaningful,
                    supporting_fact_ids_json, portfolio_revision, eligible,
                    rejection_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill,
                    assessment.subject,
                    assessment.event_id,
                    assessment.event_version,
                    assessment.action,
                    assessment.change_summary,
                    assessment.why_it_matters,
                    assessment.catalyst,
                    assessment.catalyst_timing,
                    assessment.downside_risk,
                    assessment.confidence,
                    int(assessment.meaningful),
                    json.dumps(assessment.supporting_fact_ids),
                    portfolio_revision,
                    int(eligible),
                    rejection_reason,
                    now,
                ),
            )

            if not eligible or not assessment.meaningful:
                return False

            existing = connection.execute(
                """
                SELECT 1 FROM reported_events
                WHERE skill = ? AND event_id = ? AND event_version = ?
                """,
                (skill, assessment.event_id, assessment.event_version),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    """
                    UPDATE reported_events
                    SET last_seen_at = ?
                    WHERE skill = ? AND event_id = ? AND event_version = ?
                    """,
                    (now, skill, assessment.event_id, assessment.event_version),
                )
                return False

            payload = {
                "skill": skill,
                "portfolio_revision": portfolio_revision,
                "facts": [fact.as_dict() for fact in facts],
                "analysis": assessment.as_dict(),
            }
            connection.execute(
                """
                INSERT INTO reported_events(
                    skill, event_id, event_version, first_reported_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    skill,
                    assessment.event_id,
                    assessment.event_version,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO alert_outbox(
                    skill, event_id, event_version, payload_json, status, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (
                    skill,
                    assessment.event_id,
                    assessment.event_version,
                    json.dumps(payload, sort_keys=True),
                    now,
                ),
            )
            return True

    def pending_alerts(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, payload_json
            FROM alert_outbox
            WHERE status = 'pending'
            ORDER BY id
            """
        ).fetchall()
        return [
            {"id": row["id"], "payload": json.loads(row["payload_json"])}
            for row in rows
        ]

    def mark_alert_sent(self, alert_id: int) -> None:
        self.connection.execute(
            """
            UPDATE alert_outbox
            SET status = 'sent', sent_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (utc_now(), alert_id),
        )
        self.connection.commit()

    def count(self, table: str) -> int:
        allowed = {
            "positions",
            "portfolio_events",
            "facts",
            "assessments",
            "reported_events",
            "alert_outbox",
            "runs",
        }
        if table not in allowed:
            raise ValueError("unsupported table")
        row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])
