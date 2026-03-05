"""Domain models for iCloud email classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    """Classification tier for an email message."""

    TRASH = "trash"
    KEEP_ACTIVE = "keep_active"
    KEEP_HISTORICAL = "keep_historical"
    REVIEW = "review"


TIER_COLORS: dict[Tier, str] = {
    Tier.TRASH: "red",
    Tier.KEEP_ACTIVE: "green",
    Tier.KEEP_HISTORICAL: "blue",
    Tier.REVIEW: "yellow",
}


@dataclass
class Message:
    """A single email message extracted from the Envelope Index."""

    rowid: int
    message_id: int
    conversation_id: int
    flags: int
    read: int
    flagged: int
    deleted: int
    size: int
    date_received: int
    sender_address: str
    subject: str
    mailbox_url: str
    list_id_hash: int | None
    unsubscribe_type: int | None
    automated_conversation: int
    model_category: int | None
    model_high_impact: int
    has_document_attachment: bool = False


@dataclass
class ContactProfile:
    """Reputation profile for a contact built from behavioral signals."""

    address: str
    times_sent_to: int
    last_sent_to: int | None
    times_received_from: int
    last_received_from: int | None
    read_rate: float
    reply_rate: float
    flagged_count: int
    is_bidirectional: bool
    in_system_contacts: bool = False
    name_matched_contact: bool = False


@dataclass
class SignalResult:
    """A single scoring signal contributing to classification."""

    name: str
    value: float
    weight: float
    explanation: str


@dataclass
class Classification:
    """Final classification decision for a message."""

    message_id: int
    tier: Tier
    confidence: float
    signals: str
    protected: bool
    timestamp: int
    # Phase 2 content analysis fields (optional, backward-compatible)
    content_score: float | None = None
    cluster_id: int | None = None
    cluster_label: str | None = None
    content_source: str | None = None


TIER_COLORS: dict[Tier, str] = {
    Tier.TRASH: "red",
    Tier.KEEP_ACTIVE: "green",
    Tier.KEEP_HISTORICAL: "blue",
    Tier.REVIEW: "yellow",
}
