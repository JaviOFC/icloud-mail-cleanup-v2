"""Auto-triage pre-review resolution engine.

Reduces the Review tier by auto-resolving obvious clusters (unanimity)
and consistent senders before human review, with full transparency.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean

from icloud_cleanup.models import Classification, Tier

CLUSTER_CONFIDENCE_THRESHOLD = 0.60
SENDER_CONFIDENCE_THRESHOLD = 0.55
CROSS_TIER_DOMINANCE_RATIO = 0.75
CROSS_TIER_MIN_EVIDENCE = 3


@dataclass
class AutoResolution:
    """A single auto-resolved group of messages."""

    message_ids: list[int]
    tier: Tier
    reason: str
    cluster_label: str | None
    avg_confidence: float


@dataclass
class AutoTriageResult:
    """Complete result of auto-triage passes with transparency data."""

    auto_resolved: list[AutoResolution] = field(default_factory=list)
    remaining: list[Classification] = field(default_factory=list)

    @property
    def auto_resolved_count(self) -> int:
        return sum(len(r.message_ids) for r in self.auto_resolved)

    @property
    def auto_resolved_cluster_count(self) -> int:
        return len(self.auto_resolved)

    @property
    def remaining_count(self) -> int:
        return len(self.remaining)

    @property
    def remaining_cluster_count(self) -> int:
        labels = {c.cluster_label or "Unclustered" for c in self.remaining}
        return len(labels)


def _is_noise_cluster(cluster_id: int | None) -> bool:
    return cluster_id is None or cluster_id == -1


def _check_protected_trash_safety(items: list[Classification], tier: Tier) -> bool:
    """Return True if safe to auto-resolve. False if protected items would be trashed."""
    if tier == Tier.TRASH:
        return not any(c.protected for c in items)
    return True


def auto_triage(
    classifications: list[Classification],
    sender_lookup: dict[int, str],
    *,
    review_only: bool = True,
) -> AutoTriageResult:
    """Run auto-triage passes to reduce human review burden.

    Pass 1 - Cluster unanimity: auto-resolve clusters where all emails
    share the same tier with confidence > 0.85.

    Pass 2 - Sender consistency: for remaining items, auto-resolve sender
    groups where all emails share the same tier with confidence > 0.80.

    Args:
        classifications: All classifications to triage.
        sender_lookup: Maps message_id -> sender_address.
        review_only: If True (default), only process Review-tier items.

    Returns:
        AutoTriageResult with resolved groups and remaining items.
    """
    if review_only:
        items = [c for c in classifications if c.tier == Tier.REVIEW]
    else:
        items = list(classifications)

    if not items:
        return AutoTriageResult()

    resolved: list[AutoResolution] = []
    resolved_ids: set[int] = set()

    # Pass 0: Cross-tier sender resolution
    # For senders with review-tier emails, check their non-review emails.
    # If >75% of non-review emails are in one tier with 3+ emails,
    # auto-resolve the review emails to that dominant tier.
    if review_only:
        non_review = [c for c in classifications if c.tier != Tier.REVIEW]
        if non_review:
            sender_tier_counts: dict[str, dict[Tier, int]] = defaultdict(lambda: defaultdict(int))
            for c in non_review:
                sender = sender_lookup.get(c.message_id)
                if sender:
                    sender_tier_counts[sender][c.tier] += 1

            review_sender_groups: dict[str, list[Classification]] = defaultdict(list)
            for c in items:
                sender = sender_lookup.get(c.message_id)
                if sender:
                    review_sender_groups[sender].append(c)

            for sender, review_items in review_sender_groups.items():
                tier_counts = sender_tier_counts.get(sender)
                if not tier_counts:
                    continue

                total_non_review = sum(tier_counts.values())
                if total_non_review < CROSS_TIER_MIN_EVIDENCE:
                    continue

                dominant_tier, dominant_count = max(tier_counts.items(), key=lambda x: x[1])
                ratio = dominant_count / total_non_review

                if ratio < CROSS_TIER_DOMINANCE_RATIO:
                    continue

                if not _check_protected_trash_safety(review_items, dominant_tier):
                    continue

                ids = [c.message_id for c in review_items]
                avg_conf = mean([c.confidence for c in review_items])

                resolved.append(AutoResolution(
                    message_ids=ids,
                    tier=dominant_tier,
                    reason=(
                        f"Cross-tier sender: {sender} has {dominant_count}/{total_non_review} "
                        f"non-review emails in {dominant_tier.value} ({ratio:.0%})"
                    ),
                    cluster_label=review_items[0].cluster_label,
                    avg_confidence=avg_conf,
                ))
                resolved_ids.update(ids)

    # Pass 1: Cluster unanimity
    cluster_groups: dict[int, list[Classification]] = defaultdict(list)
    for c in items:
        if not _is_noise_cluster(c.cluster_id):
            cluster_groups[c.cluster_id].append(c)

    for cluster_id, group in cluster_groups.items():
        tiers = {c.tier for c in group}
        confs = [c.confidence for c in group]

        if len(tiers) != 1:
            continue
        if min(confs) <= CLUSTER_CONFIDENCE_THRESHOLD:
            continue

        tier = next(iter(tiers))
        if not _check_protected_trash_safety(group, tier):
            continue

        avg_conf = mean(confs)
        label = group[0].cluster_label
        ids = [c.message_id for c in group]

        resolved.append(AutoResolution(
            message_ids=ids,
            tier=tier,
            reason=(
                f"Cluster unanimity: all {len(group)} emails classified as "
                f"{tier.value} with avg confidence {avg_conf:.2f}"
            ),
            cluster_label=label,
            avg_confidence=avg_conf,
        ))
        resolved_ids.update(ids)

    # Pass 2: Sender consistency (on remaining items only)
    remaining_after_p1 = [c for c in items if c.message_id not in resolved_ids]
    sender_groups: dict[str, list[Classification]] = defaultdict(list)
    for c in remaining_after_p1:
        sender = sender_lookup.get(c.message_id)
        if sender:
            sender_groups[sender].append(c)

    for sender, group in sender_groups.items():
        tiers = {c.tier for c in group}
        confs = [c.confidence for c in group]

        if len(tiers) != 1:
            continue
        if min(confs) <= SENDER_CONFIDENCE_THRESHOLD:
            continue

        tier = next(iter(tiers))
        if not _check_protected_trash_safety(group, tier):
            continue

        avg_conf = mean(confs)
        ids = [c.message_id for c in group]

        resolved.append(AutoResolution(
            message_ids=ids,
            tier=tier,
            reason=(
                f"Sender consistency: all {len(group)} emails from {sender} classified as "
                f"{tier.value} with avg confidence {avg_conf:.2f}"
            ),
            cluster_label=group[0].cluster_label,
            avg_confidence=avg_conf,
        ))
        resolved_ids.update(ids)

    remaining = [c for c in items if c.message_id not in resolved_ids]

    return AutoTriageResult(
        auto_resolved=resolved,
        remaining=remaining,
    )
