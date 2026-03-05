"""Shared test fixtures with mock Envelope Index schema."""

from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def db() -> sqlite3.Connection:
    """In-memory SQLite with Envelope Index schema and seed data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE mailboxes (
            ROWID INTEGER PRIMARY KEY,
            url TEXT NOT NULL
        );

        CREATE TABLE addresses (
            ROWID INTEGER PRIMARY KEY,
            address TEXT COLLATE NOCASE,
            comment TEXT
        );

        CREATE TABLE subjects (
            ROWID INTEGER PRIMARY KEY,
            subject TEXT
        );

        CREATE TABLE messages (
            ROWID INTEGER PRIMARY KEY,
            message_id INTEGER,
            conversation_id INTEGER DEFAULT 0,
            mailbox INTEGER REFERENCES mailboxes(ROWID),
            sender INTEGER REFERENCES addresses(ROWID),
            subject INTEGER REFERENCES subjects(ROWID),
            flags INTEGER DEFAULT 0,
            read INTEGER DEFAULT 0,
            flagged INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0,
            size INTEGER DEFAULT 0,
            date_received INTEGER DEFAULT 0,
            date_sent INTEGER DEFAULT 0,
            date_last_viewed INTEGER,
            list_id_hash INTEGER,
            unsubscribe_type INTEGER,
            automated_conversation INTEGER DEFAULT 0
        );

        CREATE TABLE recipients (
            ROWID INTEGER PRIMARY KEY,
            message INTEGER REFERENCES messages(ROWID),
            address INTEGER REFERENCES addresses(ROWID),
            type INTEGER DEFAULT 0
        );

        CREATE TABLE message_global_data (
            ROWID INTEGER PRIMARY KEY,
            message_id INTEGER,
            model_category INTEGER,
            model_high_impact INTEGER DEFAULT 0
        );

        -- Seed iCloud mailboxes
        INSERT INTO mailboxes (ROWID, url) VALUES
            (1, 'imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/INBOX'),
            (2, 'imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/Sent Messages'),
            (3, 'imap://OTHER-UUID/INBOX');

        -- Seed addresses
        INSERT INTO addresses (ROWID, address) VALUES
            (1, 'alice@example.com'),
            (2, 'Bob@Example.com'),
            (3, 'alice@example.com'),
            (4, 'carol@test.org'),
            (5, 'dave@other.com');

        -- Seed subjects
        INSERT INTO subjects (ROWID, subject) VALUES
            (1, 'Hello from Alice'),
            (2, 'Meeting reminder'),
            (3, 'Newsletter signup'),
            (4, 'Re: Hello from Alice'),
            (5, 'Sent to Dave');
    """)

    return conn


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
        (message_id, model_category, model_high_impact)
        VALUES (?, ?, ?)""",
        (message_id, model_category, model_high_impact),
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
