"""Tests for contact reputation model, protection logic, and behavioral signals."""

from __future__ import annotations

import sqlite3

from tests.helpers import insert_message, insert_recipient

from icloud_cleanup.models import ContactProfile, Message, SignalResult
from icloud_cleanup.contacts import (
    build_contact_profiles,
    check_protection_override,
    extract_behavioral_signals,
    is_protected,
)
from icloud_cleanup.scanner import (
    get_replied_conversation_ids,
    get_sent_recipients,
    scan_messages,
)


def _make_message(
    *,
    rowid: int = 1,
    message_id: int = 100,
    conversation_id: int = 0,
    flags: int = 0,
    read: int = 0,
    flagged: int = 0,
    deleted: int = 0,
    size: int = 1000,
    date_received: int = 1700000000,
    sender_address: str = "test@example.com",
    subject: str = "Test",
    mailbox_url: str = "imap://UUID/INBOX",
    list_id_hash: int | None = None,
    unsubscribe_type: int | None = None,
    automated_conversation: int = 0,
    model_category: int | None = None,
    model_high_impact: int = 0,
) -> Message:
    """Create a Message with sensible defaults for testing."""
    return Message(
        rowid=rowid,
        message_id=message_id,
        conversation_id=conversation_id,
        flags=flags,
        read=read,
        flagged=flagged,
        deleted=deleted,
        size=size,
        date_received=date_received,
        sender_address=sender_address,
        subject=subject,
        mailbox_url=mailbox_url,
        list_id_hash=list_id_hash,
        unsubscribe_type=unsubscribe_type,
        automated_conversation=automated_conversation,
        model_category=model_category,
        model_high_impact=model_high_impact,
    )


class TestBuildContactProfiles:
    """Tests for build_contact_profiles()."""

    def test_creates_profile_for_every_unique_sender(self):
        """build_contact_profiles creates a ContactProfile for every unique sender."""
        messages = [
            _make_message(sender_address="alice@example.com", date_received=1700000000),
            _make_message(sender_address="bob@example.com", date_received=1700100000),
            _make_message(sender_address="carol@test.org", date_received=1700200000),
        ]
        profiles = build_contact_profiles(messages, {}, set())
        assert len(profiles) == 3
        assert "alice@example.com" in profiles
        assert "bob@example.com" in profiles
        assert "carol@test.org" in profiles
        assert all(isinstance(p, ContactProfile) for p in profiles.values())

    def test_bidirectional_sender_in_sent_recipients(self):
        """Sender in Sent recipients has is_bidirectional=True and correct times_sent_to."""
        messages = [
            _make_message(sender_address="alice@example.com"),
        ]
        sent_recipients = {
            "alice@example.com": {"times_sent_to": 5, "last_sent_to": 1700050000},
        }
        profiles = build_contact_profiles(messages, sent_recipients, set())
        p = profiles["alice@example.com"]
        assert p.is_bidirectional is True
        assert p.times_sent_to == 5
        assert p.last_sent_to == 1700050000

    def test_non_bidirectional_sender_not_in_sent(self):
        """Sender NOT in Sent recipients has is_bidirectional=False, times_sent_to=0."""
        messages = [
            _make_message(sender_address="stranger@unknown.com"),
        ]
        profiles = build_contact_profiles(messages, {}, set())
        p = profiles["stranger@unknown.com"]
        assert p.is_bidirectional is False
        assert p.times_sent_to == 0
        assert p.last_sent_to is None

    def test_read_rate_calculation(self):
        """read_rate = (read messages from sender) / (total messages from sender)."""
        messages = [
            _make_message(sender_address="alice@example.com", message_id=1, read=1),
            _make_message(sender_address="alice@example.com", message_id=2, read=1),
            _make_message(sender_address="alice@example.com", message_id=3, read=0),
            _make_message(sender_address="alice@example.com", message_id=4, read=0),
        ]
        profiles = build_contact_profiles(messages, {}, set())
        assert profiles["alice@example.com"].read_rate == 0.5

    def test_reply_rate_combines_conversation_and_flags(self):
        """reply_rate from both conversation_id overlap AND flags bit 2."""
        replied_conv_ids = {10}
        messages = [
            # In replied conversation
            _make_message(sender_address="alice@example.com", message_id=1,
                          conversation_id=10, flags=0),
            # Has replied flag but NOT in replied conversation
            _make_message(sender_address="alice@example.com", message_id=2,
                          conversation_id=99, flags=0x4),
            # Neither replied conversation nor flag
            _make_message(sender_address="alice@example.com", message_id=3,
                          conversation_id=50, flags=0),
            # Both (should not double-count)
            _make_message(sender_address="alice@example.com", message_id=4,
                          conversation_id=10, flags=0x4),
        ]
        profiles = build_contact_profiles(messages, {}, replied_conv_ids)
        # 3 out of 4 messages have reply indicator (msg 1, 2, 4)
        assert profiles["alice@example.com"].reply_rate == 0.75

    def test_flagged_count(self):
        """flagged_count counts messages with flagged=1 from that sender."""
        messages = [
            _make_message(sender_address="alice@example.com", message_id=1, flagged=1),
            _make_message(sender_address="alice@example.com", message_id=2, flagged=0),
            _make_message(sender_address="alice@example.com", message_id=3, flagged=1),
        ]
        profiles = build_contact_profiles(messages, {}, set())
        assert profiles["alice@example.com"].flagged_count == 2

    def test_case_normalization(self):
        """Sender FOO@bar.com and foo@bar.com merge into one profile."""
        messages = [
            _make_message(sender_address="FOO@bar.com", message_id=1, read=1),
            _make_message(sender_address="foo@bar.com", message_id=2, read=0),
        ]
        profiles = build_contact_profiles(messages, {}, set())
        assert len(profiles) == 1
        assert "foo@bar.com" in profiles
        assert profiles["foo@bar.com"].times_received_from == 2
        assert profiles["foo@bar.com"].read_rate == 0.5

    def test_times_received_and_last_received(self):
        """times_received_from and last_received_from are correct."""
        messages = [
            _make_message(sender_address="alice@example.com", message_id=1,
                          date_received=1700000000),
            _make_message(sender_address="alice@example.com", message_id=2,
                          date_received=1700200000),
            _make_message(sender_address="alice@example.com", message_id=3,
                          date_received=1700100000),
        ]
        profiles = build_contact_profiles(messages, {}, set())
        p = profiles["alice@example.com"]
        assert p.times_received_from == 3
        assert p.last_received_from == 1700200000

    def test_integration_with_mock_db(self, db: sqlite3.Connection):
        """End-to-end test: scanner -> build_contact_profiles on mock DB."""
        # Insert INBOX messages
        insert_message(db, rowid=1, message_id=101, mailbox=1, sender=1, subject=1,
                        conversation_id=10, read=1, flagged=1, size=2000,
                        date_received=1700000000)
        insert_message(db, rowid=2, message_id=102, mailbox=1, sender=2, subject=2,
                        conversation_id=20, read=1, size=3000,
                        date_received=1700100000)
        insert_message(db, rowid=3, message_id=103, mailbox=1, sender=1, subject=3,
                        conversation_id=10, read=0, size=1500,
                        date_received=1700200000)

        # Sent messages
        insert_message(db, rowid=6, message_id=106, mailbox=2, sender=None, subject=4,
                        conversation_id=10, size=1000, date_received=1700050000)
        insert_recipient(db, message_rowid=6, address_rowid=1)

        messages = scan_messages(db)
        inbox_messages = [m for m in messages if "Sent" not in m.mailbox_url]
        sent_recips = get_sent_recipients(db)
        replied_convs = get_replied_conversation_ids(db)

        profiles = build_contact_profiles(inbox_messages, sent_recips, replied_convs)

        assert "alice@example.com" in profiles
        alice = profiles["alice@example.com"]
        assert alice.is_bidirectional is True
        assert alice.times_received_from == 2
        assert alice.read_rate == 0.5
        assert alice.flagged_count == 1


class TestIsProtected:
    """Tests for is_protected()."""

    def test_bidirectional_contact_is_protected(self):
        """is_protected returns True for bidirectional contact."""
        msg = _make_message()
        profile = ContactProfile(
            address="alice@example.com", times_sent_to=3, last_sent_to=1700000000,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.8, reply_rate=0.3, flagged_count=0, is_bidirectional=True,
        )
        assert is_protected(msg, profile, set()) is True

    def test_conversation_overlap_is_protected(self):
        """is_protected returns True for message in conversation with Sent message."""
        msg = _make_message(conversation_id=10)
        profile = ContactProfile(
            address="newsletter@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=50, last_received_from=1700100000,
            read_rate=0.02, reply_rate=0.0, flagged_count=0, is_bidirectional=False,
        )
        replied_conv_ids = {10, 20, 30}
        assert is_protected(msg, profile, replied_conv_ids) is True

    def test_replied_flag_is_protected(self):
        """is_protected returns True for message with flags & 0x4 (replied bit)."""
        msg = _make_message(flags=0x4)
        profile = ContactProfile(
            address="sender@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=10, last_received_from=1700100000,
            read_rate=0.5, reply_rate=0.1, flagged_count=0, is_bidirectional=False,
        )
        assert is_protected(msg, profile, set()) is True

    def test_forwarded_flag_is_protected(self):
        """is_protected returns True for message with flags & 0x10 (forwarded bit)."""
        msg = _make_message(flags=0x10)
        profile = ContactProfile(
            address="sender@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=10, last_received_from=1700100000,
            read_rate=0.5, reply_rate=0.1, flagged_count=0, is_bidirectional=False,
        )
        assert is_protected(msg, profile, set()) is True

    def test_unprotected_sender(self):
        """is_protected returns False when no protection criteria met."""
        msg = _make_message(conversation_id=99, flags=0)
        profile = ContactProfile(
            address="spammer@junk.com", times_sent_to=0, last_sent_to=None,
            times_received_from=100, last_received_from=1700100000,
            read_rate=0.01, reply_rate=0.0, flagged_count=0, is_bidirectional=False,
        )
        assert is_protected(msg, profile, {10, 20}) is False


class TestCheckProtectionOverride:
    """Tests for check_protection_override()."""

    def test_override_when_read_rate_below_5_percent(self):
        """check_protection_override returns True when read_rate below 5%."""
        profile = ContactProfile(
            address="newsletter@example.com", times_sent_to=1, last_sent_to=1700000000,
            times_received_from=100, last_received_from=1700100000,
            read_rate=0.03, reply_rate=0.01, flagged_count=0, is_bidirectional=True,
        )
        assert check_protection_override(profile) is True

    def test_no_override_when_read_rate_at_5_percent(self):
        """check_protection_override returns False when read_rate at 5%."""
        profile = ContactProfile(
            address="contact@example.com", times_sent_to=2, last_sent_to=1700000000,
            times_received_from=20, last_received_from=1700100000,
            read_rate=0.05, reply_rate=0.1, flagged_count=0, is_bidirectional=True,
        )
        assert check_protection_override(profile) is False

    def test_no_override_when_read_rate_above_5_percent(self):
        """check_protection_override returns False when read_rate above 5%."""
        profile = ContactProfile(
            address="friend@example.com", times_sent_to=5, last_sent_to=1700000000,
            times_received_from=10, last_received_from=1700100000,
            read_rate=0.80, reply_rate=0.5, flagged_count=2, is_bidirectional=True,
        )
        assert check_protection_override(profile) is False

    def test_newsletter_replied_once_pattern(self):
        """100 messages, 1 reply, 3% read rate -> protected but override fires."""
        profile = ContactProfile(
            address="newsletter@bulk.com", times_sent_to=1, last_sent_to=1700000000,
            times_received_from=100, last_received_from=1700100000,
            read_rate=0.03, reply_rate=0.01, flagged_count=0, is_bidirectional=True,
        )
        # This sender is bidirectional (replied once), so is_protected = True
        msg = _make_message(sender_address="newsletter@bulk.com")
        assert is_protected(msg, profile, set()) is True
        # But override fires due to low read rate
        assert check_protection_override(profile) is True

    def test_real_contact_pattern(self):
        """10 messages, 1 reply, 80% read rate -> protected, override does NOT fire."""
        profile = ContactProfile(
            address="friend@personal.com", times_sent_to=3, last_sent_to=1700000000,
            times_received_from=10, last_received_from=1700100000,
            read_rate=0.80, reply_rate=0.3, flagged_count=1, is_bidirectional=True,
        )
        msg = _make_message(sender_address="friend@personal.com")
        assert is_protected(msg, profile, set()) is True
        assert check_protection_override(profile) is False


class TestExtractBehavioralSignals:
    """Tests for extract_behavioral_signals()."""

    def test_returns_list_of_signal_results(self):
        """extract_behavioral_signals returns a list of SignalResult objects."""
        msg = _make_message(read=1)
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=1, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        assert isinstance(signals, list)
        assert all(isinstance(s, SignalResult) for s in signals)

    def test_read_signal_for_read_message(self):
        """Read message produces read_signal with value 1.0."""
        msg = _make_message(read=1)
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=0, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        read_sig = next(s for s in signals if s.name == "read_signal")
        assert read_sig.value == 1.0
        assert read_sig.weight == 0.15

    def test_read_signal_for_unread_message(self):
        """Unread message produces read_signal with value 0.0."""
        msg = _make_message(read=0)
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=0, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        read_sig = next(s for s in signals if s.name == "read_signal")
        assert read_sig.value == 0.0

    def test_reply_signal_uses_profile_reply_rate(self):
        """reply_signal value equals profile.reply_rate."""
        msg = _make_message()
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.42, flagged_count=0, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        reply_sig = next(s for s in signals if s.name == "reply_signal")
        assert reply_sig.value == 0.42
        assert reply_sig.weight == 0.10

    def test_flagged_signal_with_flagged_sender(self):
        """Sender with flagged_count > 0 produces flagged_signal value 1.0."""
        msg = _make_message()
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=3, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        flagged_sig = next(s for s in signals if s.name == "flagged_signal")
        assert flagged_sig.value == 1.0
        assert flagged_sig.weight == 0.05

    def test_flagged_signal_with_unflagged_sender(self):
        """Sender with flagged_count == 0 produces flagged_signal value 0.0."""
        msg = _make_message()
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=0, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        flagged_sig = next(s for s in signals if s.name == "flagged_signal")
        assert flagged_sig.value == 0.0

    def test_automation_signal_automated(self):
        """Automated message produces automation_signal value 0.0."""
        msg = _make_message(automated_conversation=2)
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=0, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        auto_sig = next(s for s in signals if s.name == "automation_signal")
        assert auto_sig.value == 0.0
        assert auto_sig.weight == 0.05

    def test_automation_signal_human(self):
        """Human message produces automation_signal value 1.0."""
        msg = _make_message(automated_conversation=0)
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=0, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        auto_sig = next(s for s in signals if s.name == "automation_signal")
        assert auto_sig.value == 1.0

    def test_unsubscribe_signal_with_unsubscribe(self):
        """Message with unsubscribe_type set produces unsubscribe_signal value 0.0."""
        msg = _make_message(unsubscribe_type=1)
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=0, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        unsub_sig = next(s for s in signals if s.name == "unsubscribe_signal")
        assert unsub_sig.value == 0.0

    def test_unsubscribe_signal_without_unsubscribe(self):
        """Message without unsubscribe_type produces unsubscribe_signal value 1.0."""
        msg = _make_message(unsubscribe_type=None)
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=0, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        unsub_sig = next(s for s in signals if s.name == "unsubscribe_signal")
        assert unsub_sig.value == 1.0

    def test_signal_explanations_present(self):
        """Every signal has a non-empty explanation string."""
        msg = _make_message(read=1, automated_conversation=0)
        profile = ContactProfile(
            address="test@example.com", times_sent_to=0, last_sent_to=None,
            times_received_from=5, last_received_from=1700100000,
            read_rate=0.6, reply_rate=0.2, flagged_count=1, is_bidirectional=False,
        )
        signals = extract_behavioral_signals(msg, profile)
        for sig in signals:
            assert isinstance(sig.explanation, str)
            assert len(sig.explanation) > 0
