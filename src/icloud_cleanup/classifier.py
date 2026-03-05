"""Classification engine — weighted composite scoring and tier assignment."""

from __future__ import annotations

import math
import time

from icloud_cleanup.contacts import check_protection_override, is_protected
from icloud_cleanup.models import (
    Classification,
    ContactProfile,
    Message,
    SignalResult,
    Tier,
)

# Signal weights (matching research spec)
CONTACT_WEIGHT = 0.30
FREQUENCY_WEIGHT = 0.15
RECENCY_WEIGHT = 0.15
READ_RATE_WEIGHT = 0.15
REPLY_RATE_WEIGHT = 0.10
APPLE_CATEGORY_WEIGHT = 0.05
AUTOMATION_WEIGHT = 0.05
FLAGGED_WEIGHT = 0.05

# Tier thresholds
TRASH_THRESHOLD = 0.95
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
) -> list[SignalResult]:
    """Compute all 8 scoring signals for a message.

    Returns a list of SignalResult objects with values in [0, 1].
    """
    now = time.time()

    # 1. Contact score: relationship strength
    if profile.is_bidirectional:
        contact_val = 1.0
        contact_expl = "bidirectional contact"
    elif profile.times_sent_to > 0:
        contact_val = 0.5
        contact_expl = "sent-to-only contact"
    else:
        contact_val = 0.0
        contact_expl = "unknown sender"

    # 2. Frequency score: engagement-weighted volume
    volume_factor = min(1.0, profile.times_received_from / 20)
    freq_val = min(1.0, profile.read_rate * volume_factor)
    freq_expl = (
        f"read_rate={profile.read_rate:.2f} * "
        f"volume_factor={volume_factor:.2f}"
    )

    # 3. Recency score: exponential decay
    age_days = (now - message.date_received) / 86400
    recency_val = math.exp(-_RECENCY_LAMBDA * max(0, age_days))
    recency_expl = f"age={age_days:.0f}d, decay=exp(-{_RECENCY_LAMBDA}*{age_days:.0f})"

    # 4. Read rate signal: profile-level read rate
    read_rate_val = profile.read_rate
    read_rate_expl = f"sender read_rate={profile.read_rate:.2f}"

    # 5. Reply rate signal: profile-level reply rate
    reply_rate_val = profile.reply_rate
    reply_rate_expl = f"sender reply_rate={profile.reply_rate:.2f}"

    # 6. Apple category signal
    apple_val = _APPLE_CATEGORY_MAP.get(message.model_category, 0.5)
    apple_expl = f"model_category={message.model_category} -> {apple_val}"

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

    return [
        SignalResult("contact_score", contact_val, CONTACT_WEIGHT, contact_expl),
        SignalResult("frequency_score", freq_val, FREQUENCY_WEIGHT, freq_expl),
        SignalResult("recency_score", recency_val, RECENCY_WEIGHT, recency_expl),
        SignalResult("read_rate_signal", read_rate_val, READ_RATE_WEIGHT, read_rate_expl),
        SignalResult("reply_rate_signal", reply_rate_val, REPLY_RATE_WEIGHT, reply_rate_expl),
        SignalResult("apple_category_signal", apple_val, APPLE_CATEGORY_WEIGHT, apple_expl),
        SignalResult("automation_signal", auto_val, AUTOMATION_WEIGHT, auto_expl),
        SignalResult("flagged_signal", flagged_val, FLAGGED_WEIGHT, flagged_expl),
    ]


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
    Trash requires (1 - confidence) >= TRASH_THRESHOLD, i.e. confidence <= 0.05.
    """
    now = time.time()
    age_days = (now - message.date_received) / 86400
    is_recent = age_days <= ACTIVE_RECENCY_DAYS
    is_engaged = profile.read_rate > 0.5 or profile.reply_rate > 0.1

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
        return Tier.TRASH

    if confidence >= KEEP_THRESHOLD:
        if is_recent and is_engaged:
            return Tier.KEEP_ACTIVE
        return Tier.KEEP_HISTORICAL

    return Tier.REVIEW


def classify_messages(
    messages: list[Message],
    profiles: dict[str, ContactProfile],
    replied_conv_ids: set[int],
) -> list[Classification]:
    """Classify every message and return a list of Classification objects."""
    now = int(time.time())
    results: list[Classification] = []

    for msg in messages:
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

        signals = compute_signals(msg, profile)
        confidence, explanation = compute_confidence(signals)
        protected = is_protected(msg, profile, replied_conv_ids)
        overridden = check_protection_override(profile) if protected else False
        tier = assign_tier(confidence, protected, overridden, profile, msg)

        results.append(Classification(
            message_id=msg.message_id,
            tier=tier,
            confidence=confidence,
            signals=explanation,
            protected=protected,
            timestamp=now,
        ))

    return results
