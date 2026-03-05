"""Tests for scanner module -- DB access, bulk extraction, sender stats."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tests.helpers import insert_message, insert_recipient

from icloud_cleanup.models import Message
from icloud_cleanup.scanner import (
    get_replied_conversation_ids,
    get_sender_stats,
    get_sent_recipients,
    open_db,
    scan_messages,
)


class TestOpenDb:
    def test_returns_connection(self, tmp_path: Path):
        """open_db returns a sqlite3 Connection with row_factory set."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()

        result = open_db(db_path)
        try:
            assert isinstance(result, sqlite3.Connection)
            row = result.execute("SELECT 1 as val").fetchone()
            assert row["val"] == 1
        finally:
            result.close()

    def test_readonly_mode(self, tmp_path: Path):
        """open_db opens in read-only mode -- writes should fail."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()

        result = open_db(db_path)
        try:
            import pytest

            with pytest.raises(sqlite3.OperationalError):
                result.execute("INSERT INTO test VALUES (1)")
        finally:
            result.close()


class TestScanMessages:
    def _seed_messages(self, db: sqlite3.Connection) -> None:
        """Populate DB with test messages for scanning."""
        # INBOX messages from 3 senders
        insert_message(db, rowid=1, message_id=101, mailbox=1, sender=1, subject=1,
                        conversation_id=10, read=1, size=2000, date_received=1700000000,
                        model_category=0, model_high_impact=0)
        insert_message(db, rowid=2, message_id=102, mailbox=1, sender=2, subject=2,
                        conversation_id=20, read=1, size=3000, date_received=1700100000,
                        model_category=3, model_high_impact=0)
        insert_message(db, rowid=3, message_id=103, mailbox=1, sender=1, subject=3,
                        conversation_id=10, read=0, size=1500, date_received=1700200000,
                        list_id_hash=99999, model_category=None, model_high_impact=0)
        insert_message(db, rowid=4, message_id=104, mailbox=1, sender=4, subject=None,
                        conversation_id=30, flags=4, read=1, size=500, date_received=1700300000,
                        unsubscribe_type=0, automated_conversation=2,
                        model_category=2, model_high_impact=1)
        # NULL sender
        insert_message(db, rowid=5, message_id=105, mailbox=1, sender=None, subject=None,
                        conversation_id=0, read=0, size=100, date_received=1700400000,
                        model_category=None, model_high_impact=0)

        # Sent messages
        insert_message(db, rowid=6, message_id=106, mailbox=2, sender=None, subject=4,
                        conversation_id=10, size=1000, date_received=1700050000)
        insert_message(db, rowid=7, message_id=107, mailbox=2, sender=None, subject=5,
                        conversation_id=40, size=800, date_received=1700150000)

        # Non-iCloud message (should be filtered out)
        insert_message(db, rowid=8, message_id=108, mailbox=3, sender=1, subject=1,
                        conversation_id=50, read=1, size=2000, date_received=1700000000,
                        model_category=0, model_high_impact=0)

        # Recipients for sent messages
        insert_recipient(db, message_rowid=6, address_rowid=1)  # sent to alice
        insert_recipient(db, message_rowid=7, address_rowid=5)  # sent to dave

    def test_returns_list_of_message_objects(self, db: sqlite3.Connection):
        self._seed_messages(db)
        messages = scan_messages(db)
        assert isinstance(messages, list)
        assert all(isinstance(m, Message) for m in messages)

    def test_only_returns_icloud_messages(self, db: sqlite3.Connection):
        self._seed_messages(db)
        messages = scan_messages(db)
        # 5 INBOX + 2 Sent = 7 iCloud messages; excludes 1 non-iCloud
        assert len(messages) == 7

    def test_correct_field_mapping(self, db: sqlite3.Connection):
        self._seed_messages(db)
        messages = scan_messages(db)
        # Find message with rowid=1
        msg1 = next(m for m in messages if m.rowid == 1)
        assert msg1.message_id == 101
        assert msg1.conversation_id == 10
        assert msg1.read == 1
        assert msg1.size == 2000
        assert msg1.date_received == 1700000000
        assert msg1.sender_address == "alice@example.com"
        assert msg1.subject == "Hello from Alice"
        assert "INBOX" in msg1.mailbox_url
        assert msg1.model_category == 0
        assert msg1.model_high_impact == 0

    def test_joins_addresses_subjects_global_data(self, db: sqlite3.Connection):
        self._seed_messages(db)
        messages = scan_messages(db)
        msg2 = next(m for m in messages if m.rowid == 2)
        assert msg2.sender_address == "Bob@Example.com"
        assert msg2.subject == "Meeting reminder"
        assert msg2.model_category == 3

    def test_handles_null_sender_coalesce(self, db: sqlite3.Connection):
        self._seed_messages(db)
        messages = scan_messages(db)
        msg5 = next(m for m in messages if m.rowid == 5)
        assert msg5.sender_address == ""

    def test_handles_null_subject_coalesce(self, db: sqlite3.Connection):
        self._seed_messages(db)
        messages = scan_messages(db)
        msg4 = next(m for m in messages if m.rowid == 4)
        assert msg4.subject == ""

    def test_nullable_fields_preserved(self, db: sqlite3.Connection):
        self._seed_messages(db)
        messages = scan_messages(db)
        msg3 = next(m for m in messages if m.rowid == 3)
        assert msg3.list_id_hash == 99999
        assert msg3.model_category is None

        msg4 = next(m for m in messages if m.rowid == 4)
        assert msg4.unsubscribe_type == 0
        assert msg4.automated_conversation == 2
        assert msg4.model_high_impact == 1


class TestGetSenderStats:
    def _seed(self, db: sqlite3.Connection) -> None:
        # alice sends 2 messages (same sender, same case)
        insert_message(db, rowid=1, message_id=101, mailbox=1, sender=1,
                        size=2000, date_received=1700000000)
        insert_message(db, rowid=2, message_id=102, mailbox=1, sender=3,
                        size=1500, date_received=1700200000)
        # Bob sends 1 (different case: "Bob@Example.com")
        insert_message(db, rowid=3, message_id=103, mailbox=1, sender=2,
                        size=3000, date_received=1700100000)
        # carol sends 1
        insert_message(db, rowid=4, message_id=104, mailbox=1, sender=4,
                        size=500, date_received=1700300000)
        # Sent message -- should NOT count in sender stats
        insert_message(db, rowid=5, message_id=105, mailbox=2, sender=None,
                        size=1000, date_received=1700050000)

    def test_returns_dict_keyed_by_lowercase(self, db: sqlite3.Connection):
        self._seed(db)
        stats = get_sender_stats(db)
        assert isinstance(stats, dict)
        assert "alice@example.com" in stats
        assert "bob@example.com" in stats
        assert "Bob@Example.com" not in stats

    def test_aggregates_count(self, db: sqlite3.Connection):
        self._seed(db)
        stats = get_sender_stats(db)
        assert stats["alice@example.com"]["count"] == 2
        assert stats["bob@example.com"]["count"] == 1

    def test_aggregates_total_size(self, db: sqlite3.Connection):
        self._seed(db)
        stats = get_sender_stats(db)
        assert stats["alice@example.com"]["total_size"] == 3500  # 2000 + 1500

    def test_date_range(self, db: sqlite3.Connection):
        self._seed(db)
        stats = get_sender_stats(db)
        assert stats["alice@example.com"]["min_date"] == 1700000000
        assert stats["alice@example.com"]["max_date"] == 1700200000

    def test_case_normalization(self, db: sqlite3.Connection):
        """Bob@Example.com and bob@example.com are the same sender."""
        self._seed(db)
        stats = get_sender_stats(db)
        assert "bob@example.com" in stats
        assert stats["bob@example.com"]["count"] == 1

    def test_excludes_sent_mailbox(self, db: sqlite3.Connection):
        self._seed(db)
        stats = get_sender_stats(db)
        # Sent message has sender=None, so no entry with empty string
        # Main check: only 3 unique senders from INBOX
        assert len(stats) == 3


class TestGetSentRecipients:
    def _seed(self, db: sqlite3.Connection) -> None:
        # Two sent messages
        insert_message(db, rowid=1, message_id=101, mailbox=2, sender=None,
                        conversation_id=10, size=1000, date_received=1700000000)
        insert_message(db, rowid=2, message_id=102, mailbox=2, sender=None,
                        conversation_id=20, size=800, date_received=1700100000)
        # INBOX message (should not affect sent recipients)
        insert_message(db, rowid=3, message_id=103, mailbox=1, sender=1,
                        size=2000, date_received=1700000000)

        # Recipients: sent msg 1 to alice, sent msg 2 to alice and dave
        insert_recipient(db, message_rowid=1, address_rowid=1)
        insert_recipient(db, message_rowid=2, address_rowid=1)
        insert_recipient(db, message_rowid=2, address_rowid=5)

    def test_returns_dict_keyed_by_lowercase(self, db: sqlite3.Connection):
        self._seed(db)
        recips = get_sent_recipients(db)
        assert isinstance(recips, dict)
        assert "alice@example.com" in recips
        assert "dave@other.com" in recips

    def test_send_count(self, db: sqlite3.Connection):
        self._seed(db)
        recips = get_sent_recipients(db)
        assert recips["alice@example.com"]["times_sent_to"] == 2
        assert recips["dave@other.com"]["times_sent_to"] == 1

    def test_last_sent_to(self, db: sqlite3.Connection):
        self._seed(db)
        recips = get_sent_recipients(db)
        assert recips["alice@example.com"]["last_sent_to"] == 1700100000

    def test_only_from_sent_mailbox(self, db: sqlite3.Connection):
        """Recipients from INBOX messages should not appear."""
        self._seed(db)
        # Add a recipient on the INBOX message -- should be ignored
        insert_recipient(db, message_rowid=3, address_rowid=4)
        recips = get_sent_recipients(db)
        assert "carol@test.org" not in recips


class TestGetRepliedConversationIds:
    def _seed(self, db: sqlite3.Connection) -> None:
        # Sent messages with conversation_ids
        insert_message(db, rowid=1, message_id=101, mailbox=2,
                        conversation_id=10, date_received=1700000000)
        insert_message(db, rowid=2, message_id=102, mailbox=2,
                        conversation_id=20, date_received=1700100000)
        # Sent message with conversation_id=0 (should be excluded)
        insert_message(db, rowid=3, message_id=103, mailbox=2,
                        conversation_id=0, date_received=1700200000)
        # INBOX message (should not appear in replied set)
        insert_message(db, rowid=4, message_id=104, mailbox=1, sender=1,
                        conversation_id=30, date_received=1700000000)

    def test_returns_set_of_ints(self, db: sqlite3.Connection):
        self._seed(db)
        result = get_replied_conversation_ids(db)
        assert isinstance(result, set)
        assert all(isinstance(cid, int) for cid in result)

    def test_includes_sent_conversation_ids(self, db: sqlite3.Connection):
        self._seed(db)
        result = get_replied_conversation_ids(db)
        assert 10 in result
        assert 20 in result

    def test_excludes_conversation_id_zero(self, db: sqlite3.Connection):
        self._seed(db)
        result = get_replied_conversation_ids(db)
        assert 0 not in result

    def test_excludes_inbox_conversations(self, db: sqlite3.Connection):
        self._seed(db)
        result = get_replied_conversation_ids(db)
        assert 30 not in result

    def test_deduplicates(self, db: sqlite3.Connection):
        """Multiple Sent messages with same conversation_id should appear once."""
        self._seed(db)
        # Add another Sent message with conversation_id=10
        insert_message(db, rowid=5, message_id=105, mailbox=2,
                        conversation_id=10, date_received=1700300000)
        result = get_replied_conversation_ids(db)
        assert result == {10, 20}
