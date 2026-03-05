"""Tests for domain models and conftest fixtures."""

from __future__ import annotations

import sqlite3

from icloud_cleanup.models import (
    Classification,
    ContactProfile,
    Message,
    SignalResult,
    Tier,
)


class TestTierEnum:
    def test_has_exactly_four_values(self):
        assert len(Tier) == 4

    def test_values(self):
        assert Tier.TRASH.value == "trash"
        assert Tier.KEEP_ACTIVE.value == "keep_active"
        assert Tier.KEEP_HISTORICAL.value == "keep_historical"
        assert Tier.REVIEW.value == "review"


class TestMessage:
    def test_all_required_fields(self):
        msg = Message(
            rowid=1,
            message_id=100,
            conversation_id=50,
            flags=0,
            read=1,
            flagged=0,
            deleted=0,
            size=2048,
            date_received=1700000000,
            sender_address="alice@example.com",
            subject="Hello",
            mailbox_url="imap://UUID/INBOX",
            list_id_hash=None,
            unsubscribe_type=None,
            automated_conversation=0,
            model_category=None,
            model_high_impact=0,
        )
        assert msg.rowid == 1
        assert msg.message_id == 100
        assert msg.conversation_id == 50
        assert msg.flags == 0
        assert msg.read == 1
        assert msg.flagged == 0
        assert msg.deleted == 0
        assert msg.size == 2048
        assert msg.date_received == 1700000000
        assert msg.sender_address == "alice@example.com"
        assert msg.subject == "Hello"
        assert msg.mailbox_url == "imap://UUID/INBOX"
        assert msg.list_id_hash is None
        assert msg.unsubscribe_type is None
        assert msg.automated_conversation == 0
        assert msg.model_category is None
        assert msg.model_high_impact == 0

    def test_nullable_fields_accept_int(self):
        msg = Message(
            rowid=1,
            message_id=100,
            conversation_id=50,
            flags=0,
            read=0,
            flagged=0,
            deleted=0,
            size=100,
            date_received=1700000000,
            sender_address="test@test.com",
            subject="Test",
            mailbox_url="imap://UUID/INBOX",
            list_id_hash=12345,
            unsubscribe_type=7,
            automated_conversation=2,
            model_category=3,
            model_high_impact=1,
        )
        assert msg.list_id_hash == 12345
        assert msg.unsubscribe_type == 7
        assert msg.model_category == 3
        assert msg.model_high_impact == 1


class TestContactProfile:
    def test_all_fields(self):
        cp = ContactProfile(
            address="alice@example.com",
            times_sent_to=5,
            last_sent_to=1700000000,
            times_received_from=20,
            last_received_from=1700100000,
            read_rate=0.85,
            reply_rate=0.15,
            flagged_count=2,
            is_bidirectional=True,
        )
        assert cp.address == "alice@example.com"
        assert cp.times_sent_to == 5
        assert cp.last_sent_to == 1700000000
        assert cp.times_received_from == 20
        assert cp.last_received_from == 1700100000
        assert cp.read_rate == 0.85
        assert cp.reply_rate == 0.15
        assert cp.flagged_count == 2
        assert cp.is_bidirectional is True

    def test_nullable_timestamps(self):
        cp = ContactProfile(
            address="bob@example.com",
            times_sent_to=0,
            last_sent_to=None,
            times_received_from=3,
            last_received_from=None,
            read_rate=0.0,
            reply_rate=0.0,
            flagged_count=0,
            is_bidirectional=False,
        )
        assert cp.last_sent_to is None
        assert cp.last_received_from is None


class TestClassification:
    def test_all_fields(self):
        c = Classification(
            message_id=100,
            tier=Tier.TRASH,
            confidence=0.97,
            signals="contact=0.0; read_rate=0.0",
            protected=False,
            timestamp=1700000000,
        )
        assert c.message_id == 100
        assert c.tier == Tier.TRASH
        assert c.confidence == 0.97
        assert c.signals == "contact=0.0; read_rate=0.0"
        assert c.protected is False
        assert c.timestamp == 1700000000

    def test_confidence_range(self):
        c = Classification(
            message_id=1,
            tier=Tier.REVIEW,
            confidence=0.5,
            signals="",
            protected=False,
            timestamp=0,
        )
        assert 0.0 <= c.confidence <= 1.0


class TestSignalResult:
    def test_all_fields(self):
        s = SignalResult(
            name="contact_score",
            value=0.9,
            weight=0.30,
            explanation="Sent 5 emails to this contact",
        )
        assert s.name == "contact_score"
        assert s.value == 0.9
        assert s.weight == 0.30
        assert s.explanation == "Sent 5 emails to this contact"


class TestConftest:
    def test_db_fixture_returns_connection(self, db: sqlite3.Connection):
        assert isinstance(db, sqlite3.Connection)

    def test_db_has_row_factory(self, db: sqlite3.Connection):
        row = db.execute("SELECT 1 as val").fetchone()
        assert row["val"] == 1

    def test_db_has_icloud_inbox(self, db: sqlite3.Connection):
        rows = db.execute(
            "SELECT url FROM mailboxes WHERE url LIKE 'imap://XXXXXXXX%/INBOX'"
        ).fetchall()
        assert len(rows) == 1

    def test_db_has_sent_mailbox(self, db: sqlite3.Connection):
        rows = db.execute(
            "SELECT url FROM mailboxes WHERE url LIKE '%Sent Messages'"
        ).fetchall()
        assert len(rows) == 1

    def test_db_has_non_icloud_mailbox(self, db: sqlite3.Connection):
        rows = db.execute(
            "SELECT url FROM mailboxes WHERE url LIKE 'imap://OTHER%'"
        ).fetchall()
        assert len(rows) == 1

    def test_db_schema_has_all_tables(self, db: sqlite3.Connection):
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {"mailboxes", "addresses", "subjects", "messages", "recipients", "message_global_data"}
        assert expected.issubset(tables)
