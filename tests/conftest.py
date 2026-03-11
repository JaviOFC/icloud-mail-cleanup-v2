"""Shared test fixtures with mock Envelope Index schema."""

from __future__ import annotations

import sqlite3

import pytest

import icloud_cleanup.scanner as _scanner
from tests.helpers import insert_message, insert_recipient  # noqa: F401 — re-export

__all__ = ["insert_message", "insert_recipient"]

TEST_UUID = "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"


@pytest.fixture(autouse=True)
def _set_icloud_uuid():
    """Set scanner.ICLOUD_UUID for tests, reset after."""
    old = _scanner.ICLOUD_UUID
    _scanner.ICLOUD_UUID = TEST_UUID
    yield
    _scanner.ICLOUD_UUID = old


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
            automated_conversation INTEGER DEFAULT 0,
            summary INTEGER REFERENCES summaries(ROWID)
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
            model_high_impact INTEGER DEFAULT 0,
            urgent INTEGER DEFAULT 0,
            model_subcategory INTEGER
        );

        CREATE TABLE server_messages (
            ROWID INTEGER PRIMARY KEY,
            message INTEGER REFERENCES messages(ROWID),
            junk_level INTEGER DEFAULT 0
        );

        CREATE TABLE attachments (
            ROWID INTEGER PRIMARY KEY,
            message INTEGER REFERENCES messages(ROWID),
            name TEXT
        );

        CREATE TABLE summaries (
            ROWID INTEGER PRIMARY KEY,
            summary TEXT
        );

        -- Seed iCloud mailboxes
        INSERT INTO mailboxes (ROWID, url) VALUES
            (1, 'imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/INBOX'),
            (2, 'imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/Sent Messages'),
            (3, 'imap://OTHER-UUID/INBOX');

        -- Seed addresses
        INSERT INTO addresses (ROWID, address, comment) VALUES
            (1, 'alice@example.com', 'Alice Smith'),
            (2, 'Bob@Example.com', 'Bob Jones'),
            (3, 'alice@example.com', 'Alice Smith'),
            (4, 'carol@test.org', NULL),
            (5, 'dave@other.com', 'Dave Wilson');

        -- Seed subjects
        INSERT INTO subjects (ROWID, subject) VALUES
            (1, 'Hello from Alice'),
            (2, 'Meeting reminder'),
            (3, 'Newsletter signup'),
            (4, 'Re: Hello from Alice'),
            (5, 'Sent to Dave');
    """)

    return conn
