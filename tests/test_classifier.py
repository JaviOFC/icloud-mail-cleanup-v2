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
    APPLE_HIGH_IMPACT_WEIGHT,
    AUTOMATION_WEIGHT,
    CONTACT_WEIGHT,
    FLAGGED_WEIGHT,
    FREQUENCY_WEIGHT,
    KEEP_THRESHOLD,
    MAILING_LIST_WEIGHT,
    NOREPLY_WEIGHT,
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
    has_document_attachment: bool = False,
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
        has_document_attachment=has_document_attachment,
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
    in_system_contacts: bool = False,
    name_matched_contact: bool = False,
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
        in_system_contacts=in_system_contacts,
        name_matched_contact=name_matched_contact,
    )


class TestComputeSignals:
    """Tests for compute_signals()."""

    def test_returns_10_signal_results(self):
        """compute_signals returns exactly 10 SignalResult objects (without feedback)."""
        msg = _make_message()
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        assert len(signals) == 10
        assert all(isinstance(s, SignalResult) for s in signals)

    def test_signal_names_match_spec(self):
        """All 10 signal names match the spec (without feedback)."""
        msg = _make_message()
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        names = {s.name for s in signals}
        expected = {
            "contact_score",
            "frequency_score",
            "recency_score",
            "reply_rate_signal",
            "apple_category_signal",
            "apple_high_impact_signal",
            "automation_signal",
            "flagged_signal",
            "mailing_list_signal",
            "noreply_signal",
        }
        assert names == expected

    def test_signal_weights_match_spec(self):
        """Signal weights match the spec constants."""
        msg = _make_message()
        profile = _make_profile()
        signals = compute_signals(msg, profile)
        weight_map = {s.name: s.weight for s in signals}
        assert weight_map["contact_score"] == CONTACT_WEIGHT
        assert weight_map["frequency_score"] == FREQUENCY_WEIGHT
        assert weight_map["recency_score"] == RECENCY_WEIGHT
        assert weight_map["reply_rate_signal"] == REPLY_RATE_WEIGHT
        assert weight_map["apple_category_signal"] == APPLE_CATEGORY_WEIGHT
        assert weight_map["apple_high_impact_signal"] == APPLE_HIGH_IMPACT_WEIGHT
        assert weight_map["automation_signal"] == AUTOMATION_WEIGHT
        assert weight_map["flagged_signal"] == FLAGGED_WEIGHT
        assert weight_map["mailing_list_signal"] == MAILING_LIST_WEIGHT
        assert weight_map["noreply_signal"] == NOREPLY_WEIGHT

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

    def test_frequency_score_bidirectional_high_volume(self):
        """Bidirectional contact with high volume produces high frequency_score."""
        msg = _make_message()
        profile = _make_profile(is_bidirectional=True, times_sent_to=5, times_received_from=100)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        # min(1.0, 100/20) = 1.0
        assert freq.value == pytest.approx(1.0, abs=0.01)

    def test_frequency_score_unknown_high_volume_capped(self):
        """Unknown sender with high volume caps at 0.3."""
        msg = _make_message()
        profile = _make_profile(is_bidirectional=False, times_sent_to=0, times_received_from=100)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        # min(0.3, 100/50) = 0.3
        assert freq.value == pytest.approx(0.3, abs=0.01)

    def test_frequency_score_unknown_low_volume(self):
        """Unknown sender with low volume gets low frequency_score (trash-leaning)."""
        msg = _make_message()
        profile = _make_profile(is_bidirectional=False, times_sent_to=0, times_received_from=5)
        signals = compute_signals(msg, profile)
        freq = next(s for s in signals if s.name == "frequency_score")
        # min(0.3, 5/50) = 0.1
        assert freq.value == pytest.approx(0.1, abs=0.01)

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
            SignalResult(name="reply_rate_signal", value=0.75, weight=0.20, explanation="t"),
            SignalResult(name="recency_score", value=0.6, weight=0.15, explanation="t"),
        ]
        _, explanation = compute_confidence(signals)
        assert "contact_score=0.90" in explanation
        assert "reply_rate_signal=0.75" in explanation
        assert "recency_score=0.60" in explanation


class TestAssignTier:
    """Tests for assign_tier()."""

    def test_protected_not_overridden_high_engagement_recent_keep_active(self):
        """Protected, not overridden, high engagement, recent -> Keep-Active."""
        now = int(time.time())
        msg = _make_message(date_received=now - 30 * 86400)  # 30 days ago
        profile = _make_profile(
            reply_rate=0.3, is_bidirectional=True,
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
            reply_rate=0.0, is_bidirectional=False,
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
        """Protected BUT overridden, trash-confidence >= 0.70 -> Trash."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400)
        profile = _make_profile(read_rate=0.02)
        tier = assign_tier(
            confidence=0.20, protected=True, overridden=True,
            profile=profile, message=msg,
        )
        assert tier == Tier.TRASH

    def test_not_protected_high_trash_confidence_trash(self):
        """Not protected, trash-confidence >= 0.70 -> Trash."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400)
        profile = _make_profile(read_rate=0.01)
        tier = assign_tier(
            confidence=0.20, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.TRASH

    def test_not_protected_high_keep_confidence_recent_engaged_active(self):
        """Not protected, keep-confidence >= 0.7, recent and engaged -> Keep-Active."""
        now = int(time.time())
        msg = _make_message(date_received=now - 30 * 86400)
        profile = _make_profile(reply_rate=0.2, is_bidirectional=True)
        tier = assign_tier(
            confidence=0.85, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_ACTIVE

    def test_not_protected_high_keep_confidence_old_historical(self):
        """Not protected, keep-confidence >= 0.7, old -> Keep-Historical."""
        now = int(time.time())
        msg = _make_message(date_received=now - 365 * 86400)
        profile = _make_profile(reply_rate=0.2, is_bidirectional=True)
        tier = assign_tier(
            confidence=0.85, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_HISTORICAL

    def test_not_protected_mid_confidence_review(self):
        """Not protected, confidence between trash and keep thresholds -> Review."""
        now = int(time.time())
        msg = _make_message(date_received=now - 200 * 86400)
        profile = _make_profile(reply_rate=0.05, is_bidirectional=False)
        tier = assign_tier(
            confidence=0.5, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.REVIEW

    def test_active_vs_historical_split_recent_and_bidirectional(self):
        """Keep-Active: within 180 days AND bidirectional."""
        now = int(time.time())
        msg = _make_message(date_received=now - 90 * 86400)  # 90 days
        profile = _make_profile(reply_rate=0.0, is_bidirectional=True)
        tier = assign_tier(
            confidence=0.8, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_ACTIVE

    def test_active_vs_historical_split_recent_but_not_engaged(self):
        """Keep-Historical: within 180 days but not bidirectional and low reply rate."""
        now = int(time.time())
        msg = _make_message(date_received=now - 90 * 86400)  # 90 days
        profile = _make_profile(reply_rate=0.05, is_bidirectional=False)
        tier = assign_tier(
            confidence=0.8, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_HISTORICAL

    def test_active_vs_historical_split_old_but_engaged(self):
        """Keep-Historical: engaged but older than 180 days."""
        now = int(time.time())
        msg = _make_message(date_received=now - 300 * 86400)  # 300 days
        profile = _make_profile(reply_rate=0.5, is_bidirectional=True)
        tier = assign_tier(
            confidence=0.8, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.KEEP_HISTORICAL

    def test_trash_threshold_boundary_at_0_30(self):
        """Confidence at 0.30 -> trash-confidence 0.70 -> Trash."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400)
        profile = _make_profile(read_rate=0.01)
        tier = assign_tier(
            confidence=0.30, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.TRASH

    def test_confidence_just_above_trash_threshold_not_trash(self):
        """Confidence of 0.31 -> trash-confidence 0.69 -> NOT Trash."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400)
        profile = _make_profile(read_rate=0.01)
        tier = assign_tier(
            confidence=0.31, protected=False, overridden=False,
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


class TestContactScoreSystemContacts:
    """Tests for contact_score with system contacts and name matching."""

    def test_contact_score_system_contacts(self):
        """in_system_contacts (not bidirectional) produces contact_score = 0.7."""
        msg = _make_message()
        profile = _make_profile(in_system_contacts=True)
        signals = compute_signals(msg, profile)
        contact = next(s for s in signals if s.name == "contact_score")
        assert contact.value == 0.7

    def test_contact_score_name_matched(self):
        """name_matched_contact (not bidirectional, not in contacts) produces contact_score = 0.4."""
        msg = _make_message()
        profile = _make_profile(name_matched_contact=True)
        signals = compute_signals(msg, profile)
        contact = next(s for s in signals if s.name == "contact_score")
        assert contact.value == 0.4

    def test_contact_score_priority_bidirectional_over_system(self):
        """Bidirectional takes priority over in_system_contacts."""
        msg = _make_message()
        profile = _make_profile(is_bidirectional=True, times_sent_to=5, in_system_contacts=True)
        signals = compute_signals(msg, profile)
        contact = next(s for s in signals if s.name == "contact_score")
        assert contact.value == 1.0

    def test_contact_score_priority_system_over_sent_to(self):
        """in_system_contacts takes priority over sent-to-only."""
        msg = _make_message()
        profile = _make_profile(
            is_bidirectional=False, times_sent_to=3,
            in_system_contacts=True,
        )
        signals = compute_signals(msg, profile)
        contact = next(s for s in signals if s.name == "contact_score")
        assert contact.value == 0.7

    def test_contact_score_priority_sent_to_over_name(self):
        """sent-to-only takes priority over name_matched_contact."""
        msg = _make_message()
        profile = _make_profile(
            is_bidirectional=False, times_sent_to=3,
            name_matched_contact=True,
        )
        signals = compute_signals(msg, profile)
        contact = next(s for s in signals if s.name == "contact_score")
        assert contact.value == 0.5

    def test_contact_score_priority_name_over_unknown(self):
        """name_matched_contact produces 0.4 instead of 0.0 for unknown."""
        msg = _make_message()
        profile_unknown = _make_profile()
        profile_named = _make_profile(name_matched_contact=True)
        signals_unknown = compute_signals(msg, profile_unknown)
        signals_named = compute_signals(msg, profile_named)
        score_unknown = next(s for s in signals_unknown if s.name == "contact_score").value
        score_named = next(s for s in signals_named if s.name == "contact_score").value
        assert score_named > score_unknown


class TestDocumentAttachmentProtection:
    """Tests for TRASH -> REVIEW bump when message has document attachments."""

    def test_trash_bumped_to_review_with_attachment(self):
        """assign_tier bumps TRASH -> REVIEW when has_document_attachment is True."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400, has_document_attachment=True)
        profile = _make_profile(read_rate=0.01)
        tier = assign_tier(
            confidence=0.20, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.REVIEW

    def test_trash_stays_trash_without_attachment(self):
        """assign_tier keeps TRASH when has_document_attachment is False."""
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400, has_document_attachment=False)
        profile = _make_profile(read_rate=0.01)
        tier = assign_tier(
            confidence=0.20, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.TRASH

    def test_attachment_does_not_affect_non_trash_tiers(self):
        """Document attachment doesn't change Review or Keep tiers."""
        now = int(time.time())
        msg = _make_message(date_received=now - 200 * 86400, has_document_attachment=True)
        profile = _make_profile(reply_rate=0.05, is_bidirectional=False)
        tier = assign_tier(
            confidence=0.5, protected=False, overridden=False,
            profile=profile, message=msg,
        )
        assert tier == Tier.REVIEW


class TestFusedClassification:
    """Tests for fuse_classification() — blending metadata + content scores."""

    def test_blends_default_weights(self):
        """Default weights: 0.6 metadata, 0.4 content."""
        from icloud_cleanup.classifier import fuse_classification
        result = fuse_classification(0.8, 0.6)
        # 0.8 * 0.6 + 0.6 * 0.4 = 0.48 + 0.24 = 0.72
        assert result == pytest.approx(0.72, abs=0.001)

    def test_blends_custom_weights(self):
        """Custom weights applied correctly."""
        from icloud_cleanup.classifier import fuse_classification
        result = fuse_classification(0.5, 1.0, metadata_weight=0.3, content_weight=0.7)
        # 0.5 * 0.3 + 1.0 * 0.7 = 0.15 + 0.70 = 0.85
        assert result == pytest.approx(0.85, abs=0.001)

    def test_returns_float_in_0_1(self):
        """Result is always a float in [0, 1]."""
        from icloud_cleanup.classifier import fuse_classification
        result = fuse_classification(1.0, 1.0)
        assert 0.0 <= result <= 1.0
        result = fuse_classification(0.0, 0.0)
        assert 0.0 <= result <= 1.0

    def test_clamps_above_1(self):
        """Values that would exceed 1.0 are clamped."""
        from icloud_cleanup.classifier import fuse_classification
        result = fuse_classification(1.0, 1.0, metadata_weight=0.8, content_weight=0.8)
        assert result == 1.0

    def test_clamps_below_0(self):
        """Values that would go below 0.0 are clamped."""
        from icloud_cleanup.classifier import fuse_classification
        result = fuse_classification(0.0, 0.0)
        assert result == 0.0


class TestReclassRules:
    """Tests for reclassify_with_content() — tier transition rules."""

    def _make_classification(
        self,
        *,
        tier: Tier = Tier.REVIEW,
        confidence: float = 0.5,
        protected: bool = False,
    ) -> Classification:
        return Classification(
            message_id=100,
            tier=tier,
            confidence=confidence,
            signals="test_signals",
            protected=protected,
            timestamp=1700000000,
        )

    def test_review_high_content_score_to_keep(self):
        """Review + high content_score (0.8) -> promoted to Keep tier.

        metadata=0.65 * 0.6 + content=0.8 * 0.4 = 0.39 + 0.32 = 0.71 -> above KEEP_THRESHOLD
        """
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.REVIEW, confidence=0.65)
        now = int(time.time())
        msg = _make_message(date_received=now - 30 * 86400)
        profile = _make_profile(reply_rate=0.3, is_bidirectional=True)
        result = reclassify_with_content(
            classification=cls, content_score=0.8,
            cluster_id=1, cluster_label="personal", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.tier in (Tier.KEEP_ACTIVE, Tier.KEEP_HISTORICAL)

    def test_review_low_content_score_to_trash(self):
        """Review + low content_score (0.2) -> demoted to Trash."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.REVIEW, confidence=0.3)
        now = int(time.time())
        msg = _make_message(date_received=now - 500 * 86400, automated_conversation=1)
        profile = _make_profile(reply_rate=0.0, is_bidirectional=False, times_sent_to=0)
        result = reclassify_with_content(
            classification=cls, content_score=0.2,
            cluster_id=2, cluster_label="newsletters", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.tier == Tier.TRASH

    def test_review_mid_content_score_stays_review(self):
        """Review + mid content_score (0.5) -> stays Review."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.REVIEW, confidence=0.5)
        now = int(time.time())
        msg = _make_message(date_received=now - 200 * 86400)
        profile = _make_profile(reply_rate=0.05, is_bidirectional=False)
        result = reclassify_with_content(
            classification=cls, content_score=0.5,
            cluster_id=3, cluster_label="mixed", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.tier == Tier.REVIEW

    def test_trash_neutral_content_stays_trash(self):
        """Trash + neutral content_score (0.5) -> stays Trash (not enough signal to promote)."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.TRASH, confidence=0.2)
        now = int(time.time())
        msg = _make_message(date_received=now - 400 * 86400)
        profile = _make_profile(reply_rate=0.0, is_bidirectional=False, times_sent_to=0)
        result = reclassify_with_content(
            classification=cls, content_score=0.5,
            cluster_id=-1, cluster_label="noise", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.tier == Tier.TRASH

    def test_trash_high_content_promotes(self):
        """Trash + high content_score (0.8) -> promoted to Review or Keep (safety net)."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.TRASH, confidence=0.1)
        now = int(time.time())
        msg = _make_message(date_received=now - 30 * 86400)
        profile = _make_profile(reply_rate=0.3, is_bidirectional=True, times_sent_to=5)
        result = reclassify_with_content(
            classification=cls, content_score=0.8,
            cluster_id=1, cluster_label="personal", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.tier != Tier.TRASH

    def test_keep_active_never_demoted(self):
        """Keep_Active + low content_score (0.1) -> stays Keep_Active (NEVER demoted)."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.KEEP_ACTIVE, confidence=0.9)
        now = int(time.time())
        msg = _make_message(date_received=now - 30 * 86400)
        profile = _make_profile(reply_rate=0.3, is_bidirectional=True)
        result = reclassify_with_content(
            classification=cls, content_score=0.1,
            cluster_id=5, cluster_label="spam", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.tier == Tier.KEEP_ACTIVE

    def test_keep_historical_never_demoted(self):
        """Keep_Historical + low content_score (0.1) -> stays Keep_Historical (NEVER demoted)."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.KEEP_HISTORICAL, confidence=0.8)
        now = int(time.time())
        msg = _make_message(date_received=now - 400 * 86400)
        profile = _make_profile(reply_rate=0.2, is_bidirectional=True)
        result = reclassify_with_content(
            classification=cls, content_score=0.1,
            cluster_id=5, cluster_label="spam", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.tier == Tier.KEEP_HISTORICAL

    def test_protected_stays_protected(self):
        """Protected message stays protected regardless of content score."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.REVIEW, confidence=0.5, protected=True)
        now = int(time.time())
        msg = _make_message(date_received=now - 200 * 86400)
        profile = _make_profile(reply_rate=0.05, is_bidirectional=False)
        result = reclassify_with_content(
            classification=cls, content_score=0.2,
            cluster_id=2, cluster_label="newsletters", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.protected is True
        assert result.tier != Tier.TRASH  # protected = never trash

    def test_updates_classification_fields(self):
        """reclassify_with_content populates content_score, cluster_id, cluster_label, content_source."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.REVIEW, confidence=0.5)
        now = int(time.time())
        msg = _make_message(date_received=now - 100 * 86400)
        profile = _make_profile(reply_rate=0.05, is_bidirectional=False)
        result = reclassify_with_content(
            classification=cls, content_score=0.6,
            cluster_id=7, cluster_label="shipping", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert result.content_score == 0.6
        assert result.cluster_id == 7
        assert result.cluster_label == "shipping"
        assert result.content_source == "body"

    def test_signals_appended(self):
        """Output signals string contains content_score and cluster info."""
        from icloud_cleanup.classifier import reclassify_with_content
        cls = self._make_classification(tier=Tier.REVIEW, confidence=0.5)
        now = int(time.time())
        msg = _make_message(date_received=now - 100 * 86400)
        profile = _make_profile(reply_rate=0.05, is_bidirectional=False)
        result = reclassify_with_content(
            classification=cls, content_score=0.6,
            cluster_id=7, cluster_label="shipping", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        assert "content_score=0.60" in result.signals
        assert "cluster=shipping" in result.signals

    def test_fused_confidence_replaces_original(self):
        """Output confidence is the fused value, not the original."""
        from icloud_cleanup.classifier import reclassify_with_content, fuse_classification
        cls = self._make_classification(tier=Tier.REVIEW, confidence=0.5)
        now = int(time.time())
        msg = _make_message(date_received=now - 100 * 86400)
        profile = _make_profile(reply_rate=0.05, is_bidirectional=False)
        result = reclassify_with_content(
            classification=cls, content_score=0.7,
            cluster_id=3, cluster_label="mixed", content_source="body",
            profile=profile, message=msg, replied_conv_ids=set(),
        )
        expected_fused = fuse_classification(0.5, 0.7)
        assert result.confidence == pytest.approx(expected_fused, abs=0.001)
