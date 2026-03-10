"""Test helper functions for inserting data into mock Envelope Index."""

from __future__ import annotations

import sqlite3


def insert_message(
    conn: sqlite3.Connection,
    *,
    rowid: int,
    message_id: int,
    mailbox: int,
    sender: int | None = None,
    subject: int | None = None,
    conversation_id: int = 0,
    flags: int = 0,
    read: int = 0,
    flagged: int = 0,
    deleted: int = 0,
    size: int = 1000,
    date_received: int = 1700000000,
    list_id_hash: int | None = None,
    unsubscribe_type: int | None = None,
    automated_conversation: int = 0,
    model_category: int | None = None,
    model_high_impact: int = 0,
    junk_level: int = 0,
    urgent: int = 0,
    model_subcategory: int | None = None,
) -> None:
    """Insert a message and its global data into the mock DB."""
    conn.execute(
        """INSERT INTO messages
        (ROWID, message_id, conversation_id, mailbox, sender, subject,
         flags, read, flagged, deleted, size, date_received,
         list_id_hash, unsubscribe_type, automated_conversation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rowid, message_id, conversation_id, mailbox, sender, subject,
         flags, read, flagged, deleted, size, date_received,
         list_id_hash, unsubscribe_type, automated_conversation),
    )
    conn.execute(
        """INSERT INTO message_global_data
        (message_id, model_category, model_high_impact, urgent, model_subcategory)
        VALUES (?, ?, ?, ?, ?)""",
        (message_id, model_category, model_high_impact, urgent, model_subcategory),
    )
    if junk_level != 0:
        conn.execute(
            "INSERT INTO server_messages (message, junk_level) VALUES (?, ?)",
            (rowid, junk_level),
        )


def insert_recipient(
    conn: sqlite3.Connection,
    *,
    message_rowid: int,
    address_rowid: int,
    recipient_type: int = 0,
) -> None:
    """Insert a recipient row for a sent message."""
    conn.execute(
        "INSERT INTO recipients (message, address, type) VALUES (?, ?, ?)",
        (message_rowid, address_rowid, recipient_type),
    )
