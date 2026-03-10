"""Tests for feedback store and new classifier signals."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from icloud_cleanup.feedback import FeedbackStore
from icloud_cleanup.classifier import (
    FEEDBACK_WEIGHT,
    MAILING_LIST_WEIGHT,
    NOREPLY_WEIGHT,
    APPLE_HIGH_IMPACT_WEIGHT,
    compute_confidence,
    compute_signals,
    classify_single,
)
from icloud_cleanup.models import ContactProfile, Message, Tier


def _make_message(**kwargs) -> Message:
    defaults = dict(
        rowid=1, message_id=100, conversation_id=0, flags=0, read=0,
        flagged=0, deleted=0, size=1000, date_received=int(time.time()) - 86400,
        sender_address="test@example.com", subject="Test",
        mailbox_url="imap://UUID/INBOX", list_id_hash=None,
        unsubscribe_type=None, automated_conversation=0,
        model_category=None, model_high_impact=0,
        has_document_attachment=False,
    )
    defaults.update(kwargs)
    return Message(**defaults)


def _make_profile(**kwargs) -> ContactProfile:
    defaults = dict(
        address="test@example.com", times_sent_to=0, last_sent_to=None,
        times_received_from=10, last_received_from=int(time.time()) - 86400,
        read_rate=0.5, reply_rate=0.1, flagged_count=0,
        is_bidirectional=False, in_system_contacts=False,
        name_matched_contact=False,
    )
    defaults.update(kwargs)
    return ContactProfile(**defaults)


# --- FeedbackStore CRUD ---

class TestFeedbackStore:

    def test_create_and_read(self, tmp_path: Path):
        db = tmp_path / "feedback.db"
        store = FeedbackStore(db)
        store.record_batch([("a@x.com", "trash"), ("b@x.com", "keep")])
        result = store.get_all()
        assert result["a@x.com"] == (1, 0)
        assert result["b@x.com"] == (0, 1)
        store.close()

    def test_upsert_increments(self, tmp_path: Path):
        db = tmp_path / "feedback.db"
        store = FeedbackStore(db)
        store.record_batch([("a@x.com", "trash")])
        store.record_batch([("a@x.com", "trash")])
        store.record_batch([("a@x.com", "keep")])
        result = store.get_all()
        assert result["a@x.com"] == (2, 1)
        store.close()

    def test_case_insensitive(self, tmp_path: Path):
        db = tmp_path / "feedback.db"
        store = FeedbackStore(db)
        store.record_batch([("A@X.COM", "trash")])
        result = store.get_all()
        assert "a@x.com" in result
        store.close()

    def test_empty_db(self, tmp_path: Path):
        db = tmp_path / "feedback.db"
        store = FeedbackStore(db)
        assert store.get_all() == {}
        store.close()

    def test_ignores_unknown_action(self, tmp_path: Path):
        db = tmp_path / "feedback.db"
        store = FeedbackStore(db)
        store.record_batch([("a@x.com", "unknown_action")])
        assert store.get_all() == {}
        store.close()


# --- Frequency signal fix ---

class TestFrequencySignalFix:

    def test_unknown_sender_1_email_is_trash_leaning(self):
        """1 email from unknown sender should be ~0.02, not 0.98."""
        msg = _make_message()
        profile = _make_profile(times_received_from=1, times_sent_to=0, is_bidirectional=False)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        assert freq.value == pytest.approx(0.02, abs=0.01)

    def test_unknown_sender_5_emails(self):
        """5 emails from unknown → 0.10."""
        msg = _make_message()
        profile = _make_profile(times_received_from=5, times_sent_to=0, is_bidirectional=False)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        assert freq.value == pytest.approx(0.10, abs=0.01)

    def test_unknown_sender_caps_at_0_3(self):
        """Unknown sender caps at 0.3 regardless of volume."""
        msg = _make_message()
        profile = _make_profile(times_received_from=100, times_sent_to=0, is_bidirectional=False)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        assert freq.value == pytest.approx(0.3, abs=0.01)

    def test_bidirectional_unchanged(self):
        """Bidirectional frequency is still volume-positive."""
        msg = _make_message()
        profile = _make_profile(times_received_from=20, is_bidirectional=True, times_sent_to=5)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        assert freq.value == pytest.approx(1.0, abs=0.01)


# --- New signals ---

class TestMailingListSignal:

    def test_list_id_present(self):
        msg = _make_message(list_id_hash=12345)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        ml = next(s for s in signals if s.name == "mailing_list_signal")
        assert ml.value == 0.1
        assert ml.weight == MAILING_LIST_WEIGHT

    def test_list_id_absent(self):
        msg = _make_message(list_id_hash=None)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        ml = next(s for s in signals if s.name == "mailing_list_signal")
        assert ml.value == 0.4


class TestNoreplySignal:

    @pytest.mark.parametrize("addr", [
        "noreply@example.com",
        "no-reply@example.com",
        "donotreply@example.com",
        "do-not-reply@example.com",
        "mailer-daemon@example.com",
        "NOREPLY@Example.COM",
    ])
    def test_noreply_patterns(self, addr: str):
        msg = _make_message(sender_address=addr)
        profile = _make_profile(address=addr.lower())
        signals = compute_signals(msg, profile)
        nr = next(s for s in signals if s.name == "noreply_signal")
        assert nr.value == 0.1
        assert nr.weight == NOREPLY_WEIGHT

    def test_normal_sender(self):
        msg = _make_message(sender_address="alice@example.com")
        profile = _make_profile(address="alice@example.com")
        signals = compute_signals(msg, profile)
        nr = next(s for s in signals if s.name == "noreply_signal")
        assert nr.value == 0.4


class TestAppleHighImpactSignal:

    def test_high_impact_set(self):
        msg = _make_message(model_high_impact=1)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        hi = next(s for s in signals if s.name == "apple_high_impact_signal")
        assert hi.value == 0.9
        assert hi.weight == APPLE_HIGH_IMPACT_WEIGHT

    def test_high_impact_not_set(self):
        msg = _make_message(model_high_impact=0)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        hi = next(s for s in signals if s.name == "apple_high_impact_signal")
        assert hi.value == 0.3


class TestFeedbackSignal:

    def test_feedback_mostly_trash(self):
        msg = _make_message(sender_address="spam@junk.com")
        profile = _make_profile(address="spam@junk.com")
        feedback = {"spam@junk.com": (10, 0)}
        signals = compute_signals(msg, profile, feedback=feedback)
        fb = next(s for s in signals if s.name == "feedback_signal")
        # (0 + 1) / (0 + 10 + 2) = 1/12 ≈ 0.083
        assert fb.value == pytest.approx(1 / 12, abs=0.01)

    def test_feedback_mostly_keep(self):
        msg = _make_message(sender_address="friend@good.com")
        profile = _make_profile(address="friend@good.com")
        feedback = {"friend@good.com": (0, 10)}
        signals = compute_signals(msg, profile, feedback=feedback)
        fb = next(s for s in signals if s.name == "feedback_signal")
        # (10 + 1) / (10 + 0 + 2) = 11/12 ≈ 0.917
        assert fb.value == pytest.approx(11 / 12, abs=0.01)

    def test_feedback_no_data_for_sender(self):
        msg = _make_message(sender_address="new@unknown.com")
        profile = _make_profile(address="new@unknown.com")
        feedback = {}
        signals = compute_signals(msg, profile, feedback=feedback)
        fb = next(s for s in signals if s.name == "feedback_signal")
        assert fb.value == 0.5

    def test_no_feedback_dict_omits_signal(self):
        msg = _make_message()
        profile = _make_profile()
        signals = compute_signals(msg, profile, feedback=None)
        names = {s.name for s in signals}
        assert "feedback_signal" not in names

    def test_with_feedback_dict_includes_signal(self):
        msg = _make_message()
        profile = _make_profile()
        signals = compute_signals(msg, profile, feedback={})
        names = {s.name for s in signals}
        assert "feedback_signal" in names


# --- End-to-end classification ---

class TestJunkDetectionEndToEnd:

    def test_unknown_sender_with_list_id_gets_trash(self):
        """Unknown sender, 1 email, mailing list → TRASH (was REVIEW before fix)."""
        now = int(time.time())
        msg = _make_message(
            sender_address="promo@random-store.com",
            date_received=now - 30 * 86400,
            list_id_hash=99999,
            model_category=3,  # Promotions
            automated_conversation=1,
            unsubscribe_type=1,
        )
        profile = _make_profile(
            address="promo@random-store.com",
            times_sent_to=0,
            times_received_from=1,
            reply_rate=0.0,
            is_bidirectional=False,
            flagged_count=0,
        )
        profiles = {"promo@random-store.com": profile}
        result = classify_single(msg, profiles, set(), now)
        assert result.tier == Tier.TRASH

    def test_no_feedback_backward_compat(self):
        """Without feedback, classification still works (no crash)."""
        now = int(time.time())
        msg = _make_message(date_received=now - 30 * 86400)
        profiles: dict[str, ContactProfile] = {}
        result = classify_single(msg, profiles, set(), now, feedback=None)
        assert isinstance(result.tier, Tier)

    def test_feedback_pushes_borderline_to_trash(self):
        """Borderline sender becomes TRASH after negative feedback."""
        now = int(time.time())
        msg = _make_message(
            sender_address="borderline@example.com",
            date_received=now - 60 * 86400,
            list_id_hash=12345,
            model_category=2,  # Updates
        )
        profile = _make_profile(
            address="borderline@example.com",
            times_sent_to=0,
            times_received_from=3,
            reply_rate=0.0,
            is_bidirectional=False,
        )
        profiles = {"borderline@example.com": profile}
        feedback = {"borderline@example.com": (5, 0)}
        result = classify_single(msg, profiles, set(), now, feedback=feedback)
        assert result.tier == Tier.TRASH
