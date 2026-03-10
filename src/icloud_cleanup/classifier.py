"""Classification engine — weighted composite scoring and tier assignment."""

from __future__ import annotations

import math
import re
import time

from icloud_cleanup.contacts import check_protection_override, is_protected
from icloud_cleanup.models import (
    Classification,
    ContactProfile,
    Message,
    SignalResult,
    Tier,
)

# Signal weights — read_rate dropped (unreliable due to bulk mark-as-read)
CONTACT_WEIGHT = 0.20
FREQUENCY_WEIGHT = 0.10
RECENCY_WEIGHT = 0.10
REPLY_RATE_WEIGHT = 0.12
APPLE_CATEGORY_WEIGHT = 0.10
APPLE_HIGH_IMPACT_WEIGHT = 0.05
AUTOMATION_WEIGHT = 0.08
FLAGGED_WEIGHT = 0.04
MAILING_LIST_WEIGHT = 0.05
NOREPLY_WEIGHT = 0.03
FEEDBACK_WEIGHT = 0.10

_NOREPLY_PATTERN = re.compile(
    r"(noreply|no-reply|donotreply|do-not-reply|mailer-daemon)", re.IGNORECASE,
)

# Tier thresholds
TRASH_THRESHOLD = 0.70
KEEP_THRESHOLD = 0.70

# Active/Historical split
ACTIVE_RECENCY_DAYS = 180

# Recency decay constant (~231-day half-life)
_RECENCY_LAMBDA = 0.003

# Apple Intelligence category value mapping
_APPLE_CATEGORY_MAP: dict[int | None, float] = {
    0: 0.8,   # Primary
    1: 0.7,   # Transactions
    2: 0.3,   # Updates
    3: 0.1,   # Promotions
    None: 0.5,
}


def compute_signals(
    message: Message,
    profile: ContactProfile,
    feedback: dict[str, tuple[int, int]] | None = None,
) -> list[SignalResult]:
    """Compute scoring signals for a message.

    Returns a list of SignalResult objects with values in [0, 1].
    read_rate is excluded — bulk mark-as-read makes it unreliable.

    feedback: optional {address: (trash_count, keep_count)} from FeedbackStore.
    When None, the feedback signal is omitted and weights auto-normalize.
    """
    now = time.time()

    # 1. Contact score: relationship strength
    if profile.is_bidirectional:
        contact_val = 1.0
        contact_expl = "bidirectional contact"
    elif profile.in_system_contacts:
        contact_val = 0.7
        contact_expl = "in system contacts (exact email)"
    elif profile.times_sent_to > 0:
        contact_val = 0.5
        contact_expl = "sent-to-only contact"
    elif profile.name_matched_contact:
        contact_val = 0.4
        contact_expl = "name-matched contact (fuzzy)"
    else:
        contact_val = 0.0
        contact_expl = "unknown sender"

    # 2. Frequency score: volume-based, direction-aware
    #    Known contacts: volume is positive (they email you and you care)
    #    Unknown senders: low volume is trash-leaning (one-off junk pattern)
    if profile.is_bidirectional:
        freq_val = min(1.0, profile.times_received_from / 20)
        freq_expl = f"bidirectional, volume={profile.times_received_from}/20"
    elif profile.times_sent_to > 0:
        freq_val = min(1.0, profile.times_received_from / 20) * 0.5
        freq_expl = f"sent-to-only, volume={profile.times_received_from}/20 * 0.5"
    else:
        freq_val = min(0.3, profile.times_received_from / 50)
        freq_expl = f"unknown, volume={profile.times_received_from}/50 capped 0.3"

    # 3. Recency score: exponential decay
    age_days = (now - message.date_received) / 86400
    recency_val = math.exp(-_RECENCY_LAMBDA * max(0, age_days))
    recency_expl = f"age={age_days:.0f}d, decay=exp(-{_RECENCY_LAMBDA}*{age_days:.0f})"

    # 4. Reply rate signal: profile-level reply rate
    reply_rate_val = profile.reply_rate
    reply_rate_expl = f"sender reply_rate={profile.reply_rate:.2f}"

    # 5. Apple category signal
    apple_val = _APPLE_CATEGORY_MAP.get(message.model_category, 0.5)
    apple_expl = f"model_category={message.model_category} -> {apple_val}"

    # 6. Apple high-impact signal
    if message.model_high_impact == 1:
        hi_val = 0.9
        hi_expl = "model_high_impact=1 (Apple thinks important)"
    else:
        hi_val = 0.5
        hi_expl = f"model_high_impact={message.model_high_impact} (neutral)"

    # 7. Automation signal: penalize automated + unsubscribe
    if message.automated_conversation > 0:
        auto_val = 0.0
        auto_expl = "automated conversation"
    else:
        auto_val = 1.0
        auto_expl = "human-sent"
    if message.unsubscribe_type is not None:
        auto_val = max(0.0, auto_val - 0.5)
        auto_expl += f", has unsubscribe (type={message.unsubscribe_type})"

    # 8. Flagged signal
    flagged_val = 1.0 if profile.flagged_count > 0 else 0.0
    flagged_expl = f"flagged_count={profile.flagged_count}"

    # 9. Mailing list signal
    if message.list_id_hash is not None:
        ml_val = 0.1
        ml_expl = "list_id_hash present (mailing list)"
    else:
        ml_val = 0.5
        ml_expl = "no list_id_hash (neutral)"

    # 10. Noreply signal
    addr_lower = message.sender_address.lower()
    if _NOREPLY_PATTERN.search(addr_lower):
        nr_val = 0.1
        nr_expl = f"noreply pattern in {addr_lower}"
    else:
        nr_val = 0.5
        nr_expl = "no noreply pattern (neutral)"

    signals = [
        SignalResult("contact_score", contact_val, CONTACT_WEIGHT, contact_expl),
        SignalResult("frequency_score", freq_val, FREQUENCY_WEIGHT, freq_expl),
        SignalResult("recency_score", recency_val, RECENCY_WEIGHT, recency_expl),
        SignalResult("reply_rate_signal", reply_rate_val, REPLY_RATE_WEIGHT, reply_rate_expl),
        SignalResult("apple_category_signal", apple_val, APPLE_CATEGORY_WEIGHT, apple_expl),
        SignalResult("apple_high_impact_signal", hi_val, APPLE_HIGH_IMPACT_WEIGHT, hi_expl),
        SignalResult("automation_signal", auto_val, AUTOMATION_WEIGHT, auto_expl),
        SignalResult("flagged_signal", flagged_val, FLAGGED_WEIGHT, flagged_expl),
        SignalResult("mailing_list_signal", ml_val, MAILING_LIST_WEIGHT, ml_expl),
        SignalResult("noreply_signal", nr_val, NOREPLY_WEIGHT, nr_expl),
    ]

    # 11. Feedback signal (optional — omitted when no feedback data available)
    if feedback is not None:
        fb = feedback.get(addr_lower)
        if fb is not None:
            trash_count, keep_count = fb
            fb_val = (keep_count + 1) / (keep_count + trash_count + 2)
            fb_expl = f"feedback trash={trash_count} keep={keep_count} -> {fb_val:.2f}"
        else:
            fb_val = 0.5
            fb_expl = "no feedback for sender (neutral)"
        signals.append(
            SignalResult("feedback_signal", fb_val, FEEDBACK_WEIGHT, fb_expl)
        )

    return signals


def compute_confidence(signals: list[SignalResult]) -> tuple[float, str]:
    """Compute weighted average confidence score from signals.

    Returns (score, explanation) where score is in [0, 1] and
    explanation lists each signal's contribution.
    """
    total_weight = sum(s.weight for s in signals)
    if total_weight == 0:
        return 0.0, "no signals"

    score = sum(s.value * s.weight for s in signals) / total_weight
    score = max(0.0, min(1.0, score))

    explanation = "; ".join(f"{s.name}={s.value:.2f}" for s in signals)
    return score, explanation


def assign_tier(
    confidence: float,
    protected: bool,
    overridden: bool,
    profile: ContactProfile,
    message: Message,
) -> Tier:
    """Assign a classification tier based on confidence and protection status.

    confidence represents "keep-worthiness" (higher = more worth keeping).
    Trash requires (1 - confidence) >= TRASH_THRESHOLD.
    """
    now = time.time()
    age_days = (now - message.date_received) / 86400
    is_recent = age_days <= ACTIVE_RECENCY_DAYS
    is_engaged = profile.reply_rate > 0.1 or profile.is_bidirectional

    if protected and not overridden:
        # Protected contacts can never be Trash
        if confidence > 0.6 and is_recent and is_engaged:
            return Tier.KEEP_ACTIVE
        if confidence > 0.4:
            return Tier.KEEP_HISTORICAL
        return Tier.REVIEW

    # Not protected OR protection overridden
    trash_confidence = 1.0 - confidence
    if trash_confidence >= TRASH_THRESHOLD:
        if message.has_document_attachment:
            return Tier.REVIEW
        return Tier.TRASH

    if confidence >= KEEP_THRESHOLD:
        if is_recent and is_engaged:
            return Tier.KEEP_ACTIVE
        return Tier.KEEP_HISTORICAL

    return Tier.REVIEW


def classify_single(
    msg: Message,
    profiles: dict[str, ContactProfile],
    replied_conv_ids: set[int],
    now: int | None = None,
    feedback: dict[str, tuple[int, int]] | None = None,
) -> Classification:
    """Classify a single message and return a Classification."""
    if now is None:
        now = int(time.time())

    addr = msg.sender_address.lower()
    profile = profiles.get(addr)
    if profile is None:
        profile = ContactProfile(
            address=addr,
            times_sent_to=0,
            last_sent_to=None,
            times_received_from=1,
            last_received_from=msg.date_received,
            read_rate=0.0,
            reply_rate=0.0,
            flagged_count=0,
            is_bidirectional=False,
        )

    signals = compute_signals(msg, profile, feedback=feedback)
    confidence, explanation = compute_confidence(signals)
    protected = is_protected(msg, profile, replied_conv_ids)
    overridden = check_protection_override(profile) if protected else False
    tier = assign_tier(confidence, protected, overridden, profile, msg)

    return Classification(
        message_id=msg.message_id,
        tier=tier,
        confidence=confidence,
        signals=explanation,
        protected=protected,
        timestamp=now,
    )


# Fused classification weights (metadata vs content)
METADATA_WEIGHT = 0.6
CONTENT_WEIGHT = 0.4


def fuse_classification(
    metadata_confidence: float,
    content_score: float,
    metadata_weight: float = METADATA_WEIGHT,
    content_weight: float = CONTENT_WEIGHT,
) -> float:
    """Blend metadata confidence with content score into single fused confidence.

    Returns a float clamped to [0.0, 1.0].
    """
    fused = metadata_confidence * metadata_weight + content_score * content_weight
    return max(0.0, min(1.0, fused))


def reclassify_with_content(
    classification: Classification,
    content_score: float,
    cluster_id: int,
    cluster_label: str,
    content_source: str,
    profile: ContactProfile,
    message: Message,
    replied_conv_ids: set[int],
) -> Classification:
    """Reclassify a message using fused metadata + content signals.

    Tier transition rules:
    - KEEP_ACTIVE / KEEP_HISTORICAL: NEVER demoted. Content fields updated only.
    - TRASH: Can be promoted if fused confidence suggests it (safety net).
    - REVIEW: Full flexibility -- assign_tier with fused confidence.
    """
    fused = fuse_classification(classification.confidence, content_score)

    # Determine new tier based on original tier's rule
    original_tier = classification.tier

    if original_tier in (Tier.KEEP_ACTIVE, Tier.KEEP_HISTORICAL):
        # Keep tiers are locked -- never demoted
        new_tier = original_tier
    elif original_tier == Tier.TRASH:
        # Trash promotion is conservative: only promote when content_score
        # shows a clear keep signal (>0.65), not just neutral noise (0.5).
        # A neutral content score should NOT override metadata's trash decision.
        if content_score > 0.65:
            protected = classification.protected
            overridden = check_protection_override(profile) if protected else False
            candidate_tier = assign_tier(fused, protected, overridden, profile, message)
            if candidate_tier in (Tier.KEEP_ACTIVE, Tier.KEEP_HISTORICAL, Tier.REVIEW):
                new_tier = candidate_tier
            else:
                new_tier = Tier.TRASH
        else:
            new_tier = Tier.TRASH
    else:
        # REVIEW: full flexibility
        protected = classification.protected
        overridden = check_protection_override(profile) if protected else False
        new_tier = assign_tier(fused, protected, overridden, profile, message)

    # Build updated signals string
    new_signals = (
        f"{classification.signals}; "
        f"content_score={content_score:.2f}, cluster={cluster_label}"
    )

    return Classification(
        message_id=classification.message_id,
        tier=new_tier,
        confidence=fused,
        signals=new_signals,
        protected=classification.protected,
        timestamp=int(time.time()),
        content_score=content_score,
        cluster_id=cluster_id,
        cluster_label=cluster_label,
        content_source=content_source,
    )


def classify_messages(
    messages: list[Message],
    profiles: dict[str, ContactProfile],
    replied_conv_ids: set[int],
    feedback: dict[str, tuple[int, int]] | None = None,
) -> list[Classification]:
    """Classify every message and return a list of Classification objects."""
    now = int(time.time())
    return [classify_single(msg, profiles, replied_conv_ids, now, feedback=feedback) for msg in messages]
