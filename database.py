from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import pandas as pd

from core.config import DATABASE_URL, DB_PATH, DEFAULT_WATCHLIST


def database_backend() -> str:
    return "postgresql" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"


def database_location() -> str:
    if database_backend() == "postgresql":
        return "PostgreSQL configuré par DATABASE_URL"
    return str(DB_PATH)


def _convert_placeholders(query: str) -> str:
    if database_backend() == "postgresql":
        return query.replace("?", "%s")
    return query


class ConnectionAdapter:
    def __init__(self, connection: Any, backend: str):
        self.raw = connection
        self.backend = backend

    def execute(self, query: str, params: Any = ()):
        return self.raw.execute(_convert_placeholders(query), params)

    def executemany(self, query: str, params: Any):
        converted_query = _convert_placeholders(query)

        if self.backend == "postgresql":
            # Psycopg 3 expose executemany() sur le curseur,
            # et non directement sur l'objet Connection.
            with self.raw.cursor() as cursor:
                cursor.executemany(converted_query, params)
            return None

        return self.raw.executemany(converted_query, params)

    def execute_statements(self, script: str) -> None:
        statements = [
            statement.strip()
            for statement in re.split(r";\s*(?:\n|$)", script)
            if statement.strip()
        ]
        for statement in statements:
            self.raw.execute(statement)


@contextmanager
def connection():
    backend = database_backend()

    if backend == "postgresql":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL est configurée, mais psycopg n'est pas installé."
            ) from exc

        conn = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=10,
        )
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

    adapter = ConnectionAdapter(conn, backend)
    try:
        yield adapter
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    name TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist (
    profile TEXT NOT NULL,
    ticker TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(profile, ticker),
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    average_cost REAL NOT NULL,
    notes TEXT DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    ticker TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold REAL,
    channel TEXT NOT NULL DEFAULT 'app',
    active INTEGER NOT NULL DEFAULT 1,
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    last_value REAL,
    last_triggered_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    profile TEXT NOT NULL,
    ticker TEXT NOT NULL,
    message TEXT NOT NULL,
    observed_value REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(alert_id) REFERENCES alerts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS macro_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    event_date TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Macro',
    notes TEXT DEFAULT '',
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Marché',
    title TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    ticker TEXT DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    name TEXT NOT NULL,
    layout_json TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile, name),
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_preferences (
    profile TEXT NOT NULL,
    pref_key TEXT NOT NULL,
    pref_value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(profile, pref_key),
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS beta_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    rating INTEGER,
    category TEXT NOT NULL DEFAULT 'Général',
    message TEXT NOT NULL,
    page_name TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    name TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist (
    profile TEXT NOT NULL,
    ticker TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(profile, ticker),
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    profile TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    average_cost DOUBLE PRECISION NOT NULL,
    notes TEXT DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    profile TEXT NOT NULL,
    ticker TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold DOUBLE PRECISION,
    channel TEXT NOT NULL DEFAULT 'app',
    active INTEGER NOT NULL DEFAULT 1,
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    last_value DOUBLE PRECISION,
    last_triggered_at TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alert_events (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL,
    profile TEXT NOT NULL,
    ticker TEXT NOT NULL,
    message TEXT NOT NULL,
    observed_value DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(alert_id) REFERENCES alerts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS macro_events (
    id BIGSERIAL PRIMARY KEY,
    profile TEXT NOT NULL,
    event_date TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Macro',
    notes TEXT DEFAULT '',
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    profile TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Marché',
    title TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    ticker TEXT DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workspaces (
    id BIGSERIAL PRIMARY KEY,
    profile TEXT NOT NULL,
    name TEXT NOT NULL,
    layout_json TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile, name),
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_preferences (
    profile TEXT NOT NULL,
    pref_key TEXT NOT NULL,
    pref_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(profile, pref_key),
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS beta_feedback (
    id BIGSERIAL PRIMARY KEY,
    profile TEXT NOT NULL,
    rating INTEGER,
    category TEXT NOT NULL DEFAULT 'Général',
    message TEXT NOT NULL,
    page_name TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(profile) REFERENCES profiles(name) ON DELETE CASCADE
);
"""


def init_db() -> None:
    script = POSTGRES_SCHEMA if database_backend() == "postgresql" else SQLITE_SCHEMA
    with connection() as conn:
        conn.execute_statements(script)


def database_health() -> tuple[bool, str]:
    try:
        with connection() as conn:
            row = conn.execute("SELECT 1 AS ok").fetchone()
        value = row["ok"] if isinstance(row, dict) else row["ok"]
        return bool(value == 1), database_backend()
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def ensure_profile(profile: str) -> str:
    clean = (profile or "principal").strip().lower()
    with connection() as conn:
        conn.execute(
            "INSERT INTO profiles(name) VALUES (?) ON CONFLICT(name) DO NOTHING",
            (clean,),
        )
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM watchlist WHERE profile = ?",
            (clean,),
        ).fetchone()
        count = int(row["total"])
        if count == 0:
            conn.executemany(
                """
                INSERT INTO watchlist(profile, ticker)
                VALUES (?, ?)
                ON CONFLICT(profile, ticker) DO NOTHING
                """,
                [(clean, ticker) for ticker in DEFAULT_WATCHLIST],
            )
    return clean


def delete_profile_data(profile: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM profiles WHERE name=?", (profile,))


def get_watchlist(profile: str) -> list[str]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE profile=? ORDER BY created_at",
            (profile,),
        ).fetchall()
    return [row["ticker"] for row in rows]


def add_watchlist(profile: str, ticker: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO watchlist(profile, ticker)
            VALUES (?, ?)
            ON CONFLICT(profile, ticker) DO NOTHING
            """,
            (profile, ticker.upper()),
        )


def remove_watchlist(profile: str, ticker: str) -> None:
    with connection() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE profile=? AND ticker=?",
            (profile, ticker.upper()),
        )


def get_positions(profile: str) -> pd.DataFrame:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, ticker, quantity, average_cost, notes, updated_at
            FROM positions WHERE profile=? ORDER BY ticker
            """,
            (profile,),
        ).fetchall()
    columns = ["id", "ticker", "quantity", "average_cost", "notes", "updated_at"]
    return pd.DataFrame([dict(row) for row in rows], columns=columns)


def replace_positions(profile: str, positions: pd.DataFrame) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM positions WHERE profile=?", (profile,))
        records: list[tuple[Any, ...]] = []
        for _, row in positions.iterrows():
            ticker = str(row.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            quantity = float(row.get("quantity", 0) or 0)
            average_cost = float(row.get("average_cost", 0) or 0)
            notes = str(row.get("notes", "") or "")
            if quantity == 0:
                continue
            records.append((profile, ticker, quantity, average_cost, notes))
        if records:
            conn.executemany(
                """
                INSERT INTO positions(profile, ticker, quantity, average_cost, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                records,
            )


def add_alert(
    profile: str,
    ticker: str,
    alert_type: str,
    operator: str,
    threshold: float | None,
    channel: str = "app",
    cooldown_minutes: int = 60,
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO alerts(
                profile, ticker, alert_type, operator, threshold, channel,
                cooldown_minutes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile,
                ticker.upper(),
                alert_type,
                operator,
                threshold,
                channel,
                cooldown_minutes,
            ),
        )


def get_alerts(profile: str | None = None, active_only: bool = False) -> pd.DataFrame:
    clauses = []
    params: list[Any] = []
    if profile:
        clauses.append("profile=?")
        params.append(profile)
    if active_only:
        clauses.append("active=1")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    query = f"SELECT * FROM alerts{where} ORDER BY created_at DESC"
    with connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def delete_alert(alert_id: int) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM alerts WHERE id=?", (int(alert_id),))


def set_alert_active(alert_id: int, active: bool) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE alerts SET active=? WHERE id=?",
            (1 if active else 0, int(alert_id)),
        )


def record_alert_trigger(
    alert_id: int,
    profile: str,
    ticker: str,
    message: str,
    observed_value: float | None,
) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with connection() as conn:
        conn.execute(
            """
            UPDATE alerts
            SET last_triggered_at=?, last_value=?
            WHERE id=?
            """,
            (now, observed_value, alert_id),
        )
        conn.execute(
            """
            INSERT INTO alert_events(
                alert_id, profile, ticker, message, observed_value, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (alert_id, profile, ticker, message, observed_value, now),
        )
        conn.execute(
            """
            INSERT INTO notifications(
                profile, category, title, message, ticker, severity, created_at
            ) VALUES (?, 'Alerte', ?, ?, ?, 'warning', ?)
            """,
            (profile, f"Alerte déclenchée · {ticker}", message, ticker, now),
        )


def update_alert_value(alert_id: int, observed_value: float | None) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE alerts SET last_value=? WHERE id=?",
            (observed_value, alert_id),
        )


def get_alert_events(profile: str, limit: int = 100) -> pd.DataFrame:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM alert_events
            WHERE profile=? ORDER BY created_at DESC LIMIT ?
            """,
            (profile, limit),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def get_macro_events(profile: str) -> pd.DataFrame:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, event_date, title, category, notes
            FROM macro_events WHERE profile=? ORDER BY event_date
            """,
            (profile,),
        ).fetchall()
    return pd.DataFrame(
        [dict(row) for row in rows],
        columns=["id", "event_date", "title", "category", "notes"],
    )


def replace_macro_events(profile: str, events: pd.DataFrame) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM macro_events WHERE profile=?", (profile,))
        records: list[tuple[Any, ...]] = []
        for _, row in events.iterrows():
            title = str(row.get("title", "")).strip()
            event_date = str(row.get("event_date", "")).strip()
            if not title or not event_date:
                continue
            records.append(
                (
                    profile,
                    event_date,
                    title,
                    str(row.get("category", "Macro") or "Macro"),
                    str(row.get("notes", "") or ""),
                )
            )
        if records:
            conn.executemany(
                """
                INSERT INTO macro_events(profile, event_date, title, category, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                records,
            )


def add_notification(
    profile: str,
    title: str,
    message: str = "",
    category: str = "Marché",
    ticker: str = "",
    severity: str = "info",
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO notifications(
                profile, category, title, message, ticker, severity
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (profile, category, title, message, ticker.upper(), severity),
        )


def get_notifications(
    profile: str,
    unread_only: bool = False,
    limit: int = 100,
) -> pd.DataFrame:
    where = "profile=?" + (" AND is_read=0" if unread_only else "")
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM notifications
            WHERE {where}
            ORDER BY created_at DESC LIMIT ?
            """,
            (profile, int(limit)),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def mark_notification_read(notification_id: int, is_read: bool = True) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE notifications SET is_read=? WHERE id=?",
            (1 if is_read else 0, int(notification_id)),
        )


def mark_all_notifications_read(profile: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE notifications SET is_read=1 WHERE profile=?",
            (profile,),
        )


def save_workspace(
    profile: str,
    name: str,
    layout_json: str,
    active: bool = False,
) -> None:
    with connection() as conn:
        if active:
            conn.execute(
                "UPDATE workspaces SET is_active=0 WHERE profile=?",
                (profile,),
            )
        conn.execute(
            """
            INSERT INTO workspaces(
                profile, name, layout_json, is_active, updated_at
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(profile, name) DO UPDATE SET
                layout_json=excluded.layout_json,
                is_active=excluded.is_active,
                updated_at=CURRENT_TIMESTAMP
            """,
            (profile, name.strip(), layout_json, 1 if active else 0),
        )


def get_workspaces(profile: str) -> pd.DataFrame:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM workspaces
            WHERE profile=? ORDER BY is_active DESC, name
            """,
            (profile,),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def delete_workspace(profile: str, name: str) -> None:
    with connection() as conn:
        conn.execute(
            "DELETE FROM workspaces WHERE profile=? AND name=?",
            (profile, name),
        )


def set_preference(profile: str, key: str, value: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO user_preferences(
                profile, pref_key, pref_value, updated_at
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(profile, pref_key) DO UPDATE SET
                pref_value=excluded.pref_value,
                updated_at=CURRENT_TIMESTAMP
            """,
            (profile, key, value),
        )


def get_preference(profile: str, key: str, default: str = "") -> str:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT pref_value FROM user_preferences
            WHERE profile=? AND pref_key=?
            """,
            (profile, key),
        ).fetchone()
    return str(row["pref_value"]) if row else default


def add_feedback(
    profile: str,
    message: str,
    rating: int | None = None,
    category: str = "Général",
    page_name: str = "",
    contact_email: str = "",
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO beta_feedback(
                profile, rating, category, message, page_name, contact_email
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                profile,
                rating,
                category,
                message.strip(),
                page_name.strip(),
                contact_email.strip(),
            ),
        )


def get_feedback(limit: int = 500) -> pd.DataFrame:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM beta_feedback
            ORDER BY created_at DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])
