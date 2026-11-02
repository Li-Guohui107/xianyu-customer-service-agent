"""用标准库 sqlite3 记住同一会话里的买家消息和草稿。"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SessionNotFoundError(LookupError):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    product_id TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    risk_level TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS sent_replies (
    chat_key TEXT NOT NULL,
    buyer_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (chat_key, buyer_message)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
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
                columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
                if "product_id" not in columns:
                    connection.execute("ALTER TABLE sessions ADD COLUMN product_id TEXT")
                connection.commit()
            finally:
                connection.close()
            self._ready = True

    def _connect(self) -> sqlite3.Connection:
        self._ensure()
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def create_session(self) -> str:
        session_id = uuid.uuid4().hex
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO sessions (id, created_at) VALUES (?, ?)",
                (session_id, _now()),
            )
            connection.commit()
        finally:
            connection.close()
        return session_id

    def get_focus_product(self, session_id: str) -> str | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT product_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None or not row["product_id"]:
            return None
        return str(row["product_id"])

    def set_focus_product(self, session_id: str, product_id: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "UPDATE sessions SET product_id = ? WHERE id = ?",
                (product_id, session_id),
            )
            connection.commit()
        finally:
            connection.close()

    def ensure_session(self, session_id: str) -> str:
        if self.exists(session_id):
            return session_id
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO sessions (id, created_at) VALUES (?, ?)",
                (session_id, _now()),
            )
            connection.commit()
        finally:
            connection.close()
        return session_id

    def has_sent_reply(self, chat_key: str, buyer_message: str) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT 1 FROM sent_replies WHERE chat_key = ? AND buyer_message = ?",
                (chat_key, buyer_message),
            ).fetchone()
        finally:
            connection.close()
        return row is not None

    def remember_sent_reply(self, chat_key: str, buyer_message: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT OR IGNORE INTO sent_replies (chat_key, buyer_message, created_at)
                VALUES (?, ?, ?)
                """,
                (chat_key, buyer_message, _now()),
            )
            connection.commit()
        finally:
            connection.close()

    def exists(self, session_id: str) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT 1 FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()
        return row is not None

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        risk_level: str | None,
    ) -> None:
        if role not in {"buyer", "assistant"}:
            raise ValueError("无法识别的消息角色")
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO messages (session_id, role, content, risk_level, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, risk_level, _now()),
            )
            connection.commit()
        finally:
            connection.close()

    def list_messages(self, session_id: str) -> list[dict]:
        if not self.exists(session_id):
            raise SessionNotFoundError(session_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT role, content, risk_level
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def recent_messages(self, session_id: str, limit: int = 6) -> list[dict]:
        messages = self.list_messages(session_id)
        return messages[-limit:]
