"""Contact reputation model, protection logic, and behavioral signal extraction."""

from __future__ import annotations

from collections import defaultdict

from icloud_cleanup.models import ContactProfile, Message, SignalResult


def build_contact_profiles(
    messages: list[Message],
    sent_recipients: dict[str, dict],
    replied_conv_ids: set[int],
) -> dict[str, ContactProfile]:
    """Build a ContactProfile for every unique sender in messages.

    Groups by lowercase sender address. Combines sent recipient data
    for bidirectional detection and reply detection from both
    conversation_id overlap and flags bit 2.
    """
    grouped: dict[str, list[Message]] = defaultdict(list)
    for msg in messages:
        key = msg.sender_address.lower()
        if key:
            grouped[key].append(msg)

    profiles: dict[str, ContactProfile] = {}
    for address, msgs in grouped.items():
        total = len(msgs)
        read_count = sum(1 for m in msgs if m.read)
        reply_count = sum(
            1 for m in msgs
            if m.conversation_id in replied_conv_ids or m.flags & 0x4
        )
        flagged_count = sum(1 for m in msgs if m.flagged)
        last_received = max(m.date_received for m in msgs)

        sent_info = sent_recipients.get(address)
        if sent_info:
            times_sent_to = sent_info["times_sent_to"]
            last_sent_to = sent_info["last_sent_to"]
            is_bidirectional = True
        else:
            times_sent_to = 0
            last_sent_to = None
            is_bidirectional = False

        profiles[address] = ContactProfile(
            address=address,
            times_sent_to=times_sent_to,
            last_sent_to=last_sent_to,
            times_received_from=total,
            last_received_from=last_received,
            read_rate=read_count / total,
            reply_rate=reply_count / total,
            flagged_count=flagged_count,
            is_bidirectional=is_bidirectional,
        )

    return profiles


def is_protected(
    message: Message,
    profile: ContactProfile,
    replied_conv_ids: set[int],
) -> bool:
    """Determine if a message is protected from Trash classification.

    Protection criteria (any one is sufficient):
    - Sender is bidirectional (exists in Sent recipients)
    - Message conversation_id overlaps with Sent conversations
    - Message has replied flag (flags & 0x4)
    - Message has forwarded flag (flags & 0x10)
    """
    if profile.is_bidirectional:
        return True
    if message.conversation_id in replied_conv_ids:
        return True
    if message.flags & 0x4:
        return True
    if message.flags & 0x10:
        return True
    return False


def check_protection_override(profile: ContactProfile) -> bool:
    """Check if a protected sender's protection should be overridden.

    Catches newsletters accidentally replied to once but never engaged with.
    Override fires when read_rate is below 5% -- the sender is technically
    bidirectional but the user never reads their messages.
    """
    return profile.read_rate < 0.05


def extract_behavioral_signals(
    message: Message,
    profile: ContactProfile,
) -> list[SignalResult]:
    """Extract per-message behavioral signals as typed SignalResult objects.

    Returns signals for: read state, reply rate, flagged history,
    automation detection, and unsubscribe presence.
    """
    read_val = 1.0 if message.read else 0.0
    flagged_val = 1.0 if profile.flagged_count > 0 else 0.0
    auto_val = 0.0 if message.automated_conversation > 0 else 1.0
    unsub_val = 0.0 if message.unsubscribe_type is not None else 1.0

    return [
        SignalResult(
            name="read_signal",
            value=read_val,
            weight=0.15,
            explanation=f"read={message.read} ({'message was read by user' if message.read else 'message was not read'})",
        ),
        SignalResult(
            name="reply_signal",
            value=profile.reply_rate,
            weight=0.10,
            explanation=f"reply_rate={profile.reply_rate:.2f} (sender reply engagement rate)",
        ),
        SignalResult(
            name="flagged_signal",
            value=flagged_val,
            weight=0.05,
            explanation=f"flagged_count={profile.flagged_count} ({'sender has flagged messages' if profile.flagged_count > 0 else 'no flagged messages from sender'})",
        ),
        SignalResult(
            name="automation_signal",
            value=auto_val,
            weight=0.05,
            explanation=f"automated_conversation={message.automated_conversation} ({'automated/machine-generated' if message.automated_conversation > 0 else 'human-sent message'})",
        ),
        SignalResult(
            name="unsubscribe_signal",
            value=unsub_val,
            weight=0.05,
            explanation=f"unsubscribe_type={message.unsubscribe_type} ({'has unsubscribe option' if message.unsubscribe_type is not None else 'no unsubscribe option'})",
        ),
    ]
