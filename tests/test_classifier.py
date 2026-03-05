"""Tests for classification engine — scoring, tier assignment, and message classification."""

from __future__ import annotations

import math
import time

from icloud_cleanup.models import (
    Classification,
    ContactProfile,
    Message,
    SignalResult,
    Tier,
)
from icloud_cleanup.classifier import (
    ACTIVE_RECENCY_DAYS,
    APPLE_CATEGORY_WEIGHT,
    AUTOMATION_WEIGHT,
    CONTACT_WEIGHT,
    FLAGGED_WEIGHT,
    FREQUENCY_WEIGHT,
    KEEP_THRESHOLD,
    READ_RATE_WEIGHT,
    RECENCY_WEIGHT,
    REPLY_RATE_WEIGHT,
    TRASH_THRESHOLD,
    assign_tier,
    classify_messages,
    compute_confidence,
    compute_signals,
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


def _make_profile(
    *,
    address: str = "test@example.com",
    times_sent_to: int = 0,
    last_sent_to: int | None = None,
    times_received_from: int = 10,
    last_received_from: int | None = 1700000000,
    read_rate: float = 0.5,
    reply_rate: float = 0.1,
    flagged_count: int = 0,
    is_bidirectional: bool = False,
) -> ContactProfile:
    """Create a ContactProfile with sensible defaults for testing."""
    return ContactProfile(
        address=address,
        times_sent_to=times_sent_to,
        last_sent_to=last_sent_to,
        times_received_from=times_received_from,
        last_received_from=last_received_from,
        read_rate=read_rate,
        reply_rate=reply_rate,
        flagged_count=flagged_count,
        is_bidirectional=is_bidirectional,
    )


class TestComputeSignals:
    """Tests for compute_signals()."""

    def test_returns_8_signal_results(self):
        """compute_signals returns exactly 8 SignalResult objects."""
        msg = _make_message()
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        assert len(signals) == 8
        assert all(isinstance(s, SignalResult) for s in signals)

    def test_signal_names_match_spec(self):
        """All 8 signal names match the research spec."""
        msg = _make_message()
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        names = {s.name for s in signals}
        expected = {
            "contact_score",
            "frequency_score",
            "recency_score",
            "read_rate_signal",
            "reply_rate_signal",
            "apple_category_signal",
            "automation_signal",
            "flagged_signal",
        }
        assert names == expected

    def test_signal_weights_match_spec(self):
        """Signal weights match the research spec constants."""
        msg = _make_message()
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        weight_map = {s.name: s.weight for s in signals}
        assert weight_map["contact_score"] == CONTACT_WEIGHT
        assert weight_map["frequency_score"] == FREQUENCY_WEIGHT
        assert weight_map["recency_score"] == RECENCY_WEIGHT
        assert weight_map["read_rate_signal"] == READ_RATE_WEIGHT
        assert weight_map["reply_rate_signal"] == REPLY_RATE_WEIGHT
        assert weight_map["apple_category_signal"] == APPLE_CATEGORY_WEIGHT
        assert weight_map["automation_signal"] == AUTOMATION_WEIGHT
        assert weight_map["flagged_signal"] == FLAGGED_WEIGHT

    def test_contact_score_bidirectional(self):
        """Bidirectional contact produces contact_score = 1.0."""
        msg = _make_message()
        profile = _make_profile(is_bidirectional=True, times_sent_to=5)
        signals = compute_signals(msg, profile)
        contact = next(s for s in signals if s.name == "contact_score")
        assert contact.value == 1.0

    def test_contact_score_sent_to_only(self):
        """Sent-to-only (times_sent_to > 0 but not bidirectional) produces contact_score = 0.5."""
        msg = _make_message()
        profile = _make_profile(is_bidirectional=False, times_sent_to=3)
        signals = compute_signals(msg, profile)
        contact = next(s for s in signals if s.name == "contact_score")
        assert contact.value == 0.5

    def test_contact_score_unknown_sender(self):
        """Unknown sender (times_sent_to=0, not bidirectional) produces contact_score = 0.0."""
        msg = _make_message()
        profile = _make_profile(is_bidirectional=False, times_sent_to=0)
        signals = compute_signals(msg, profile)
        contact = next(s for s in signals if s.name == "contact_score")
        assert contact.value == 0.0

    def test_frequency_score_high_volume_low_read(self):
        """High volume sender with low read rate produces low frequency_score."""
        msg = _make_message()
        profile = _make_profile(read_rate=0.05, times_received_from=100)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        # 0.05 * min(1.0, 100/20) = 0.05 * 1.0 = 0.05
        assert freq.value == pytest.approx(0.05, abs=0.01)

    def test_frequency_score_low_volume_high_read(self):
        """Low volume sender with high read rate produces moderate frequency_score."""
        msg = _make_message()
        profile = _make_profile(read_rate=0.9, times_received_from=5)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        # 0.9 * min(1.0, 5/20) = 0.9 * 0.25 = 0.225
        assert freq.value == pytest.approx(0.225, abs=0.01)

    def test_recency_score_zero_age(self):
        """Message received just now has recency_score near 1.0."""
        now = int(time.time())
        msg = _make_message(date_received=now)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        recency = next(s for s in signals if s.name == "recency_score")
        assert recency.value == pytest.approx(1.0, abs=0.01)

    def test_recency_score_one_year_half_life(self):
        """Message from ~365 days ago has recency_score near 0.5."""
        now = int(time.time())
        one_year_ago = now - (365 * 86400)
        msg = _make_message(date_received=one_year_ago)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        recency = next(s for s in signals if s.name == "recency_score")
        # exp(-0.003 * 365) ~ 0.334, which is roughly half-life territory
        # The plan says "~1-year half-life", ln(2)/0.003 = 231 days
        # So at 365 days: exp(-0.003 * 365) ~ 0.334
        assert 0.2 < recency.value < 0.6

    def test_recency_score_uses_exponential_decay(self):
        """Recency score follows exp(-0.003 * age_days)."""
        now = int(time.time())
        age_days = 100
        msg = _make_message(date_received=now - age_days * 86400)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        recency = next(s for s in signals if s.name == "recency_score")
        expected = math.exp(-0.003 * age_days)
        assert recency.value == pytest.approx(expected, abs=0.01)

    def test_apple_category_primary(self):
        """Apple category 0 (Primary) produces signal value 0.8."""
        msg = _make_message(model_category=0)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        apple = next(s for s in signals if s.name == "apple_category_signal")
        assert apple.value == 0.8

    def test_apple_category_transactions(self):
        """Apple category 1 (Transactions) produces signal value 0.7."""
        msg = _make_message(model_category=1)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        apple = next(s for s in signals if s.name == "apple_category_signal")
        assert apple.value == 0.7

    def test_apple_category_updates(self):
        """Apple category 2 (Updates) produces signal value 0.3."""
        msg = _make_message(model_category=2)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        apple = next(s for s in signals if s.name == "apple_category_signal")
        assert apple.value == 0.3

    def test_apple_category_promotions(self):
        """Apple category 3 (Promotions) produces signal value 0.1."""
        msg = _make_message(model_category=3)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        apple = next(s for s in signals if s.name == "apple_category_signal")
        assert apple.value == 0.1

    def test_apple_category_none(self):
        """Apple category None produces signal value 0.5."""
        msg = _make_message(model_category=None)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        apple = next(s for s in signals if s.name == "apple_category_signal")
        assert apple.value == 0.5

    def test_automation_signal_human_no_unsubscribe(self):
        """Human message without unsubscribe has automation_signal = 1.0."""
        msg = _make_message(automated_conversation=0, unsubscribe_type=None)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        auto = next(s for s in signals if s.name == "automation_signal")
        assert auto.value == 1.0

    def test_automation_signal_automated(self):
        """Automated message has automation_signal = 0.0."""
        msg = _make_message(automated_conversation=2, unsubscribe_type=None)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        auto = next(s for s in signals if s.name == "automation_signal")
        assert auto.value == 0.0

    def test_automation_signal_human_with_unsubscribe(self):
        """Human message with unsubscribe has automation_signal = 0.5."""
        msg = _make_message(automated_conversation=0, unsubscribe_type=1)
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        auto = next(s for s in signals if s.name == "automation_signal")
        assert auto.value == 0.5

    def test_flagged_signal_with_flagged(self):
        """Sender with flagged_count > 0 produces flagged_signal = 1.0."""
        msg = _make_message()
        profile = _make_profile(flagged_count=3)
        signals = compute_signals(msg, profile)
        flagged = next(s for s in signals if s.name == "flagged_signal")
        assert flagged.value == 1.0

    def test_flagged_signal_without_flagged(self):
        """Sender with flagged_count == 0 produces flagged_signal = 0.0."""
        msg = _make_message()
        profile = _make_profile(flagged_count=0)
        signals = compute_signals(msg, profile)
        flagged = next(s for s in signals if s.name == "flagged_signal")
        assert flagged.value == 0.0


import pytest


class TestComputeConfidence:
    """Tests for compute_confidence()."""

    def test_returns_float_and_string(self):
        """compute_confidence returns a (float, str) tuple."""
        signals = [
            SignalResult(name="sig1", value=0.8, weight=0.5, explanation="test"),
            SignalResult(name="sig2", value=0.6, weight=0.5, explanation="test"),
        ]
        score, explanation = compute_confidence(signals)
        assert isinstance(score, float)
        assert isinstance(explanation, str)

    def test_weighted_average(self):
        """Confidence is the weighted average of all signals."""
        signals = [
            SignalResult(name="sig1", value=1.0, weight=0.6, explanation="test"),
            SignalResult(name="sig2", value=0.0, weight=0.4, explanation="test"),
        ]
        score, _ = compute_confidence(signals)
        # (1.0 * 0.6 + 0.0 * 0.4) / (0.6 + 0.4) = 0.6
        assert score == pytest.approx(0.6, abs=0.001)

    def test_range_0_to_1(self):
        """Confidence score is always in the 0-1 range."""
        signals_max = [
            SignalResult(name="s", value=1.0, weight=1.0, explanation="t")
        ]
        signals_min = [
            SignalResult(name="s", value=0.0, weight=1.0, explanation="t")
        ]
        assert compute_confidence(signals_max)[0] == pytest.approx(1.0)
        assert compute_confidence(signals_min)[0] == pytest.approx(0.0)

    def test_explanation_lists_all_signals(self):
        """Explanation string contains all signal names with their values."""
        signals = [
            SignalResult(name="contact_score", value=0.9, weight=0.3, explanation="t"),
            SignalResult(name="read_rate_signal", value=0.75, weight=0.15, explanation="t"),
            SignalResult(name="recency_score", value=0.6, weight=0.15, explanation="t"),
        ]
        _, explanation = compute_confidence(signals)
        assert "contact_score=0.90" in explanation
        assert "read_rate_signal=0.75" in explanation
        assert "recency_score=0.60" in explanation


class TestAssignTier:
    """Tests for assign_tier()."""

    def test_protected_not_overridden_high_engagement_recent_keep_active(self):
        """Protected, not overridden, high engagement, recent -> Keep-Active."""
        now = int(time.time())
        msg = _make_message(date_received=now - 30 * 86400)  # 30 days ago
        profile = _make_profile(
            read_rate=0.8, reply_rate=0.3,
            last_received_from=now - 30 * 86400,
        )
        tier = assign_tier(
            confidence=0.8, protected=True, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_ACTIVE

    def test_protected_not_overridden_low_engagement_old_keep_historical(self):
        """Protected, not overridden, low engagement, old -> Keep-Historical."""
        now = int(time.time())
        msg = _make_message(date_received=now - 400 * 86400)  # 400 days ago
        profile = _make_profile(
            read_rate=0.2, reply_rate=0.0,
            last_received_from=now - 400 * 86400,
        )
        tier = assign_tier(
            confidence=0.5, protected=True, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_HISTORICAL

    def test_protected_not_overridden_ambiguous_review(self):
        """Protected, not overridden, ambiguous (low confidence) -> Review (never Trash)."""
        now = int(time.time())
        msg = _make_message(date_received=now - 200 * 86400)
        profile = _make_profile(read_rate=0.1, reply_rate=0.0)
        tier = assign_tier(
            confidence=0.2, protected=True, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.REVIEW
        assert tier != Tier.TRASH

    def test_protected_overridden_high_trash_confidence_trash(self):
        """Protected BUT overridden, keep-confidence <= 0.05 (trash-confidence >= 0.95) -> Trash."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400)
        profile = _make_profile(read_rate=0.02)
        tier = assign_tier(
            confidence=0.03, protected=True, overridden=True,
            profile=profile, message=msg,
        )
        assert tier == Tier.TRASH

    def test_not_protected_high_trash_confidence_trash(self):
        """Not protected, keep-confidence <= 0.05 -> Trash."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400)
        profile = _make_profile(read_rate=0.01)
        tier = assign_tier(
            confidence=0.04, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.TRASH

    def test_not_protected_high_keep_confidence_recent_engaged_active(self):
        """Not protected, keep-confidence >= 0.7, recent and engaged -> Keep-Active."""
        now = int(time.time())
        msg = _make_message(date_received=now - 30 * 86400)
        profile = _make_profile(read_rate=0.8, reply_rate=0.2)
        tier = assign_tier(
            confidence=0.85, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_ACTIVE

    def test_not_protected_high_keep_confidence_old_historical(self):
        """Not protected, keep-confidence >= 0.7, old -> Keep-Historical."""
        now = int(time.time())
        msg = _make_message(date_received=now - 365 * 86400)
        profile = _make_profile(read_rate=0.8, reply_rate=0.2)
        tier = assign_tier(
            confidence=0.85, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_HISTORICAL

    def test_not_protected_mid_confidence_review(self):
        """Not protected, confidence between 0.05 and 0.7 -> Review."""
        now = int(time.time())
        msg = _make_message(date_received=now - 200 * 86400)
        profile = _make_profile(read_rate=0.3, reply_rate=0.05)
        tier = assign_tier(
            confidence=0.4, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.REVIEW

    def test_active_vs_historical_split_recent_and_engaged(self):
        """Keep-Active: within 180 days AND (read_rate > 0.5 OR reply_rate > 0.1)."""
        now = int(time.time())
        msg = _make_message(date_received=now - 90 * 86400)  # 90 days
        profile = _make_profile(read_rate=0.6, reply_rate=0.0)
        tier = assign_tier(
            confidence=0.8, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_ACTIVE

    def test_active_vs_historical_split_recent_but_not_engaged(self):
        """Keep-Historical: within 180 days but low engagement."""
        now = int(time.time())
        msg = _make_message(date_received=now - 90 * 86400)  # 90 days
        profile = _make_profile(read_rate=0.3, reply_rate=0.05)
        tier = assign_tier(
            confidence=0.8, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_HISTORICAL

    def test_active_vs_historical_split_old_but_engaged(self):
        """Keep-Historical: engaged but older than 180 days."""
        now = int(time.time())
        msg = _make_message(date_received=now - 300 * 86400)  # 300 days
        profile = _make_profile(read_rate=0.9, reply_rate=0.5)
        tier = assign_tier(
            confidence=0.8, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_HISTORICAL

    def test_trash_threshold_boundary_at_0_05(self):
        """Confidence exactly at 0.05 should NOT be Trash (needs strictly <= 0.05)."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400)
        profile = _make_profile(read_rate=0.01)
        tier = assign_tier(
            confidence=0.05, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.TRASH

    def test_confidence_just_above_trash_threshold_not_trash(self):
        """Confidence of 0.06 should NOT be Trash."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400)
        profile = _make_profile(read_rate=0.01)
        tier = assign_tier(
            confidence=0.06, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier != Tier.TRASH


class TestClassifyMessages:
    """Tests for classify_messages()."""

    def test_returns_classification_for_every_message(self):
        """classify_messages returns one Classification per input message."""
        messages = [
            _make_message(message_id=1, sender_address="alice@example.com"),
            _make_message(message_id=2, sender_address="bob@example.com"),
            _make_message(message_id=3, sender_address="carol@test.org"),
        ]
        profiles = {
            "alice@example.com": _make_profile(address="alice@example.com", is_bidirectional=True),
            "bob@example.com": _make_profile(address="bob@example.com"),
            "carol@test.org": _make_profile(address="carol@test.org"),
        }
        results = classify_messages(messages, profiles, set())
        assert len(results) == 3
        assert all(isinstance(r, Classification) for r in results)

    def test_every_message_gets_valid_tier(self):
        """Every Classification has a valid Tier enum value."""
        messages = [
            _make_message(message_id=1, sender_address="alice@example.com"),
            _make_message(message_id=2, sender_address="unknown@spam.com"),
        ]
        profiles = {
            "alice@example.com": _make_profile(address="alice@example.com"),
        }
        results = classify_messages(messages, profiles, set())
        assert len(results) == 2
        for r in results:
            assert isinstance(r.tier, Tier)

    def test_unknown_sender_gets_default_profile(self):
        """Message from unknown sender (no profile) still gets classified."""
        messages = [
            _make_message(message_id=1, sender_address="unknown@nowhere.com"),
        ]
        results = classify_messages(messages, {}, set())
        assert len(results) == 1
        assert isinstance(results[0].tier, Tier)

    def test_classification_has_correct_message_id(self):
        """Each Classification's message_id matches the input message."""
        messages = [
            _make_message(message_id=42, sender_address="alice@example.com"),
            _make_message(message_id=99, sender_address="bob@example.com"),
        ]
        profiles = {
            "alice@example.com": _make_profile(address="alice@example.com"),
            "bob@example.com": _make_profile(address="bob@example.com"),
        }
        results = classify_messages(messages, profiles, set())
        result_ids = {r.message_id for r in results}
        assert result_ids == {42, 99}

    def test_classification_has_timestamp(self):
        """Each Classification has a non-zero timestamp."""
        messages = [_make_message(message_id=1)]
        results = classify_messages(messages, {}, set())
        assert results[0].timestamp > 0

    def test_protected_message_never_trashed(self):
        """Protected bidirectional contact message is never classified as Trash."""
        now = int(time.time())
        messages = [
            _make_message(
                message_id=1,
                sender_address="friend@example.com",
                date_received=now - 30 * 86400,
                read=1,
            ),
        ]
        profiles = {
            "friend@example.com": _make_profile(
                address="friend@example.com",
                is_bidirectional=True,
                times_sent_to=10,
                read_rate=0.9,
                reply_rate=0.4,
                flagged_count=2,
            ),
        }
        results = classify_messages(messages, profiles, set())
        assert results[0].tier != Tier.TRASH
        assert results[0].protected is True

    def test_case_insensitive_profile_lookup(self):
        """Profile lookup by sender address is case insensitive."""
        messages = [
            _make_message(message_id=1, sender_address="ALICE@Example.COM"),
        ]
        profiles = {
            "alice@example.com": _make_profile(
                address="alice@example.com",
                is_bidirectional=True,
                read_rate=0.9,
            ),
        }
        results = classify_messages(messages, profiles, set())
        assert len(results) == 1
        assert results[0].protected is True
