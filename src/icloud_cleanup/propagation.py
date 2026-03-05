"""Post-review propagation engine.

After a review decision, suggests applying the same action to similar
senders: same domain, alias detection, subdomain matches.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from icloud_cleanup.models import Classification

# Common email providers where domain matching is useless
COMMON_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "yahoo.co.uk", "hotmail.com", "outlook.com",
    "icloud.com", "me.com", "mac.com", "aol.com", "protonmail.com",
    "live.com", "msn.com", "ymail.com", "mail.com", "zoho.com",
    "proton.me", "fastmail.com", "tutanota.com",
})


@dataclass
class PropagationSuggestion:
    """A suggestion to propagate a review decision to similar senders."""

    source_sender: str
    target_senders: list[str]
    target_message_ids: list[int]
    reason: str
    suggested_action: str


def _extract_domain(email: str) -> str:
    """Extract domain from email address."""
    parts = email.lower().split("@")
    return parts[1] if len(parts) == 2 else ""


def _extract_base_domain(domain: str) -> str:
    """Extract base domain from a possibly-subdomained domain.

    marketing.store.com -> store.com
    store.com -> store.com
    """
    parts = domain.split(".")
    if len(parts) > 2:
        return ".".join(parts[-2:])
    return domain


def find_propagation_targets(
    decided_sender: str,
    action: str,
    all_classifications: list[Classification],
    sender_lookup: dict[int, str],
    already_decided: set[int],
) -> list[PropagationSuggestion]:
    """Find similar senders to suggest propagating a decision to.

    Strategies:
    1. Domain match: same @domain (skip common providers)
    2. Subdomain match: same base domain (e.g., marketing.store.com and support.store.com)
    3. Alias detection: senders sharing local-part prefix patterns
    """
    if not all_classifications or not sender_lookup:
        return []

    decided_domain = _extract_domain(decided_sender)
    if not decided_domain:
        return []

    decided_base_domain = _extract_base_domain(decided_domain)

    # Build reverse lookup: sender -> list of (message_id, classification)
    sender_messages: dict[str, list[tuple[int, Classification]]] = defaultdict(list)
    for c in all_classifications:
        mid = c.message_id
        if mid in already_decided:
            continue
        sender = sender_lookup.get(mid, "").lower()
        if sender and sender != decided_sender.lower():
            sender_messages[sender].append((mid, c))

    suggestions: list[PropagationSuggestion] = []
    suggested_senders: set[str] = set()

    # Strategy 1: Domain match (exact domain, skip common providers)
    if decided_domain not in COMMON_DOMAINS:
        domain_targets: dict[str, list[int]] = defaultdict(list)
        for sender, msgs in sender_messages.items():
            sender_domain = _extract_domain(sender)
            if sender_domain == decided_domain and sender not in suggested_senders:
                for mid, _ in msgs:
                    domain_targets[sender].append(mid)

        if domain_targets:
            all_target_senders = list(domain_targets.keys())
            all_target_ids = [mid for ids in domain_targets.values() for mid in ids]
            suggestions.append(PropagationSuggestion(
                source_sender=decided_sender,
                target_senders=all_target_senders,
                target_message_ids=all_target_ids,
                reason=f"Same domain: @{decided_domain}",
                suggested_action=action,
            ))
            suggested_senders.update(all_target_senders)

    # Strategy 2: Subdomain match (same base domain, different subdomains)
    if decided_domain not in COMMON_DOMAINS:
        subdomain_targets: dict[str, list[int]] = defaultdict(list)
        for sender, msgs in sender_messages.items():
            if sender in suggested_senders:
                continue
            sender_domain = _extract_domain(sender)
            sender_base = _extract_base_domain(sender_domain)
            if (
                sender_base == decided_base_domain
                and sender_domain != decided_domain
            ):
                for mid, _ in msgs:
                    subdomain_targets[sender].append(mid)

        if subdomain_targets:
            all_target_senders = list(subdomain_targets.keys())
            all_target_ids = [mid for ids in subdomain_targets.values() for mid in ids]
            suggestions.append(PropagationSuggestion(
                source_sender=decided_sender,
                target_senders=all_target_senders,
                target_message_ids=all_target_ids,
                reason=f"Same base domain: {decided_base_domain}",
                suggested_action=action,
            ))
            suggested_senders.update(all_target_senders)

    return suggestions
