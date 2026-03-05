"""Contact reputation model, protection logic, and behavioral signal extraction."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from icloud_cleanup.models import ContactProfile, Message, SignalResult

_SERVICE_DOMAINS = frozenset({
    "amazon.com", "paypal.com", "calendly.com", "linkedin.com",
    "facebook.com", "facebookmail.com", "craigslist.org", "alignable.com",
    "punchbowl.com", "evite.com", "basecamp.com", "substack.com",
})

_ADDRESSBOOK_DIR = Path.home() / "Library/Application Support/AddressBook/Sources"


@dataclass
class SystemContacts:
    """Contacts loaded from macOS AddressBook databases."""

    emails: set[str] = field(default_factory=set)
    names: set[tuple[str, str]] = field(default_factory=set)
    own_names: set[tuple[str, str]] = field(default_factory=set)


def load_system_contacts(
    sent_recipients: dict[str, dict],
    addressbook_dir: Path | None = None,
) -> SystemContacts:
    """Load contacts from macOS AddressBook SQLite databases.

    Globs all AddressBook-v22.abcddb files under Sources/*/,
    extracts emails and first+last name pairs. Detects the user's
    own names by finding contact records whose emails overlap with
    sent_recipients.
    """
    base = addressbook_dir or _ADDRESSBOOK_DIR
    if not base.exists():
        return SystemContacts()

    db_paths = list(base.glob("*/AddressBook-v22.abcddb"))
    if not db_paths:
        return SystemContacts()

    sent_set = {addr.lower() for addr in sent_recipients}
    emails: set[str] = set()
    names: set[tuple[str, str]] = set()
    own_names: set[tuple[str, str]] = set()

    for db_path in db_paths:
        try:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.OperationalError:
            continue

        try:
            # Extract all email addresses
            for row in conn.execute(
                "SELECT ZADDRESSNORMALIZED FROM ZABCDEMAILADDRESS WHERE ZADDRESSNORMALIZED IS NOT NULL"
            ):
                addr = row["ZADDRESSNORMALIZED"].lower().strip()
                if addr:
                    emails.add(addr)

            # Extract name pairs linked to emails
            for row in conn.execute("""
                SELECT DISTINCT
                    r.ZFIRSTNAME, r.ZLASTNAME,
                    e.ZADDRESSNORMALIZED
                FROM ZABCDRECORD r
                JOIN ZABCDEMAILADDRESS e ON e.ZOWNER = r.Z_PK
                WHERE r.ZFIRSTNAME IS NOT NULL AND r.ZLASTNAME IS NOT NULL
                  AND LENGTH(r.ZFIRSTNAME) >= 2 AND LENGTH(r.ZLASTNAME) >= 2
                  AND e.ZADDRESSNORMALIZED IS NOT NULL
            """):
                first = row["ZFIRSTNAME"].lower().strip()
                last = row["ZLASTNAME"].lower().strip()
                addr = row["ZADDRESSNORMALIZED"].lower().strip()
                if first and last:
                    names.add((first, last))
                    if addr in sent_set:
                        own_names.add((first, last))
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    return SystemContacts(emails=emails, names=names, own_names=own_names)


def build_contact_profiles(
    messages: list[Message],
    sent_recipients: dict[str, dict],
    replied_conv_ids: set[int],
    system_contacts: SystemContacts | None = None,
    sender_display_names: dict[str, str] | None = None,
) -> dict[str, ContactProfile]:
    """Build a ContactProfile for every unique sender in messages.

    Groups by lowercase sender address. Combines sent recipient data
    for bidirectional detection and reply detection from both
    conversation_id overlap and flags bit 2.

    Optionally enriches with macOS system contacts (exact email match)
    and sender display name fuzzy matching against contact names.
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

        # System contacts: exact email match
        in_system = False
        if system_contacts and address in system_contacts.emails:
            in_system = True

        # Name-based fuzzy match
        name_matched = False
        if system_contacts and sender_display_names and not in_system:
            display_name = sender_display_names.get(address, "")
            if display_name:
                name_matched = _check_name_match(
                    display_name, address, system_contacts,
                )

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
            in_system_contacts=in_system,
            name_matched_contact=name_matched,
        )

    return profiles


def _check_name_match(
    display_name: str,
    address: str,
    system_contacts: SystemContacts,
) -> bool:
    """Check if a sender display name matches a system contact name.

    Guards: skip "(via " proxy names, service domains, and own names.
    """
    if " via " in display_name or "(via " in display_name:
        return False

    domain = address.rsplit("@", 1)[-1].lower() if "@" in address else ""
    if domain in _SERVICE_DOMAINS:
        return False

    display_lower = display_name.lower()
    for first, last in system_contacts.names:
        if (first, last) in system_contacts.own_names:
            continue
        if display_lower.startswith(f"{first} {last}"):
            return True

    return False


def is_protected(
    message: Message,
    profile: ContactProfile,
    replied_conv_ids: set[int],
) -> bool:
    """Determine if a message is protected from Trash classification.

    Protection criteria (any one is sufficient):
    - Sender is bidirectional (exists in Sent recipients)
    - Sender's exact email is in macOS system contacts
    - Message conversation_id overlaps with Sent conversations
    - Message has replied flag (flags & 0x4)
    - Message has forwarded flag (flags & 0x10)

    Note: name_matched_contact does NOT grant protection (too many
    potential false positives). The scoring boost is enough.
    """
    if profile.is_bidirectional:
        return True
    if profile.in_system_contacts:
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
