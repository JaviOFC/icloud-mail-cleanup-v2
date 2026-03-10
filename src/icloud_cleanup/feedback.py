"""Feedback store — persists user decisions per sender for classification feedback loop."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DEFAULT_FEEDBACK_DB = Path.home() / ".icloud-cleanup" / "feedback.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sender_feedback (
    address TEXT PRIMARY KEY,
    trash_count INTEGER DEFAULT 0,
    keep_count INTEGER DEFAULT 0,
    last_updated INTEGER
);
"""


class FeedbackStore:
    """SQLite-backed store for per-sender decision feedback."""

    def __init__(self, path: Path = DEFAULT_FEEDBACK_DB) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def record_batch(self, items: list[tuple[str, str]]) -> None:
        """Upsert a batch of (address, action) pairs.

        action should be "trash" or "keep".
        """
        now = int(time.time())
        for address, action in items:
            addr = address.lower()
            if action == "trash":
                self._conn.execute(
                    "INSERT INTO sender_feedback (address, trash_count, keep_count, last_updated) "
                    "VALUES (?, 1, 0, ?) "
                    "ON CONFLICT(address) DO UPDATE SET "
                    "trash_count = trash_count + 1, last_updated = ?",
                    (addr, now, now),
                )
            elif action == "keep":
                self._conn.execute(
                    "INSERT INTO sender_feedback (address, trash_count, keep_count, last_updated) "
                    "VALUES (?, 0, 1, ?) "
                    "ON CONFLICT(address) DO UPDATE SET "
                    "keep_count = keep_count + 1, last_updated = ?",
                    (addr, now, now),
                )
        self._conn.commit()

    def get_all(self) -> dict[str, tuple[int, int]]:
        """Return {address: (trash_count, keep_count)} for all senders with feedback."""
        rows = self._conn.execute(
            "SELECT address, trash_count, keep_count FROM sender_feedback"
        ).fetchall()
        return {addr: (trash, keep) for addr, trash, keep in rows}

    def close(self) -> None:
        self._conn.close()
