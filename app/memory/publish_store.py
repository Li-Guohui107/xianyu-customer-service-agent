"""定时发布的时间点和当天结果。跟会话记在同一个 SQLite 文件里。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS publish_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS publish_slots (
    slot_id TEXT PRIMARY KEY,
    time_of_day TEXT NOT NULL,
    product_id TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    position INTEGER NOT NULL,
    price TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS listing_samples (
    position INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS publish_runs (
    slot_id TEXT NOT NULL,
    run_date TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (slot_id, run_date, source)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PublishStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._ready = False
        self._lock = threading.Lock()

    def _ensure(self) -> None:
        with self._lock:
            if self._ready:
                return
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
            try:
                connection.executescript(SCHEMA)
                connection.execute(
                    "INSERT OR IGNORE INTO publish_settings (id, enabled) VALUES (1, 0)"
                )
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(publish_slots)")
                }
                if "price" not in columns:
                    connection.execute(
                        "ALTER TABLE publish_slots ADD COLUMN price TEXT NOT NULL DEFAULT ''"
                    )
                if "title" not in columns:
                    connection.execute(
                        "ALTER TABLE publish_slots ADD COLUMN title TEXT NOT NULL DEFAULT ''"
                    )
                if "description" not in columns:
                    connection.execute(
                        "ALTER TABLE publish_slots ADD COLUMN description TEXT NOT NULL DEFAULT ''"
                    )
                run_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(publish_runs)")
                }
                if "source" not in run_columns:
                    connection.execute(
                        """
                        CREATE TABLE publish_runs_next (
                            slot_id TEXT NOT NULL,
                            run_date TEXT NOT NULL,
                            source TEXT NOT NULL,
                            status TEXT NOT NULL,
                            detail TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            PRIMARY KEY (slot_id, run_date, source)
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO publish_runs_next (slot_id, run_date, source, status, detail, created_at)
                        SELECT slot_id, run_date, 'schedule', status, detail, created_at FROM publish_runs
                        """
                    )
                    connection.execute("DROP TABLE publish_runs")
                    connection.execute("ALTER TABLE publish_runs_next RENAME TO publish_runs")
                connection.commit()
            finally:
                connection.close()
            self._ready = True

    def _connect(self) -> sqlite3.Connection:
        self._ensure()
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def load(self) -> dict:
        connection = self._connect()
        try:
            enabled = connection.execute("SELECT enabled FROM publish_settings WHERE id = 1").fetchone()
            rows = connection.execute(
                """
                SELECT slot_id, time_of_day, product_id, enabled, price, title, description
                FROM publish_slots
                ORDER BY position ASC, time_of_day ASC
                """
            ).fetchall()
        finally:
            connection.close()
        return {
            "enabled": bool(enabled["enabled"]) if enabled else False,
            "slots": [
                {
                    "slot_id": row["slot_id"],
                    "time": row["time_of_day"],
                    "product_id": row["product_id"],
                    "enabled": bool(row["enabled"]),
                    "price": row["price"] or "",
                    "title": row["title"] or "",
                    "description": row["description"] or "",
                }
                for row in rows
            ],
        }

    def replace(self, *, enabled: bool, slots: list[dict]) -> dict:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM publish_slots")
            connection.execute(
                "INSERT INTO publish_settings (id, enabled) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled",
                (1 if enabled else 0,),
            )
            for position, slot in enumerate(slots):
                connection.execute(
                    """
                    INSERT INTO publish_slots (
                        slot_id, time_of_day, product_id, enabled, position, price, title, description
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slot["slot_id"],
                        slot["time"],
                        slot["product_id"],
                        1 if slot.get("enabled", True) else 0,
                        position,
                        slot.get("price") or "",
                        slot.get("title") or "",
                        slot.get("description") or "",
                    ),
                )
            connection.commit()
        finally:
            connection.close()
        return self.load()

    def list_samples(self) -> list[dict]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT title, body FROM listing_samples ORDER BY position ASC"
            ).fetchall()
        finally:
            connection.close()
        return [{"title": row["title"], "body": row["body"]} for row in rows]

    def replace_samples(self, samples: list[dict]) -> list[dict]:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM listing_samples")
            for position, sample in enumerate(samples):
                connection.execute(
                    "INSERT INTO listing_samples (position, title, body) VALUES (?, ?, ?)",
                    (position, sample["title"], sample["body"]),
                )
            connection.commit()
        finally:
            connection.close()
        return self.list_samples()

    def get_slot(self, slot_id: str) -> dict | None:
        for slot in self.load()["slots"]:
            if slot["slot_id"] == slot_id:
                return slot
        return None

    def published_ids(self, day: date) -> set[str]:
        """今天已经由定时发出去的时间点。手动「现在发」不占这个名额。"""
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT slot_id FROM publish_runs
                WHERE run_date = ? AND status = 'published' AND source = 'schedule'
                """,
                (day.isoformat(),),
            ).fetchall()
        finally:
            connection.close()
        return {row["slot_id"] for row in rows}

    def runs_on(self, day: date) -> list[dict]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT slot_id, status, detail
                FROM publish_runs
                WHERE run_date = ?
                ORDER BY created_at ASC
                """,
                (day.isoformat(),),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def mark_run(self, slot_id: str, day: date, status: str, detail: str, *, source: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO publish_runs (slot_id, run_date, source, status, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(slot_id, run_date, source) DO UPDATE SET
                    status = excluded.status,
                    detail = excluded.detail,
                    created_at = excluded.created_at
                """,
                (slot_id, day.isoformat(), source, status, detail[:180], _now()),
            )
            connection.commit()
        finally:
            connection.close()
