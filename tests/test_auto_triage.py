"""Tests for auto-triage pre-review resolution engine."""

from __future__ import annotations

import time

import pytest

from icloud_cleanup.auto_triage import AutoTriageResult, auto_triage
from icloud_cleanup.models import Classification, Tier


def _make_classification(
    message_id: int,
    tier: Tier = Tier.REVIEW,
    confidence: float = 0.5,
    *,
    cluster_id: int | None = None,
    cluster_label: str | None = None,
    protected: bool = False,
) -> Classification:
    return Classification(
        message_id=message_id,
        tier=tier,
        confidence=confidence,
        signals="test_signal",
        protected=protected,
        timestamp=int(time.time()),
        cluster_id=cluster_id,
        cluster_label=cluster_label,
    )


class TestClusterUnanimity:
    """Pass 1: auto-resolve clusters where all emails share same tier + high confidence."""

    def test_resolves_unanimous_cluster(self) -> None:
        """Cluster where all items are same tier with confidence > 0.85."""
        items = [
            _make_classification(i, Tier.TRASH, 0.90, cluster_id=1, cluster_label="spam")
            for i in range(1, 6)
        ]
        sender_lookup = {i: f"spam{i}@junk.com" for i in range(1, 6)}

        result = auto_triage(items, sender_lookup, review_only=False)

        assert isinstance(result, AutoTriageResult)
        assert result.auto_resolved_count == 5
        assert result.remaining_count == 0
        assert len(result.auto_resolved) == 1
        assert result.auto_resolved[0].tier == Tier.TRASH

    def test_skips_low_confidence_cluster(self) -> None:
        """Cluster with confidence <= 0.60 should NOT be auto-resolved."""
        items = [
            _make_classification(1, Tier.REVIEW, 0.55, cluster_id=1, cluster_label="maybe"),
            _make_classification(2, Tier.REVIEW, 0.50, cluster_id=1, cluster_label="maybe"),
        ]
        sender_lookup = {1: "a@test.com", 2: "b@test.com"}

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_count == 0
        assert result.remaining_count == 2

    def test_skips_mixed_tier_cluster(self) -> None:
        """Cluster with mixed tiers should NOT be auto-resolved by either pass."""
        items = [
            _make_classification(1, Tier.TRASH, 0.90, cluster_id=1, cluster_label="mixed"),
            _make_classification(2, Tier.REVIEW, 0.90, cluster_id=1, cluster_label="mixed"),
        ]
        # Same sender so sender consistency also skips (mixed tiers)
        sender_lookup = {1: "same@test.com", 2: "same@test.com"}

        result = auto_triage(items, sender_lookup, review_only=False)
        assert result.auto_resolved_count == 0

    def test_skips_noise_cluster(self) -> None:
        """Noise cluster (id=-1 or None) should be skipped by cluster unanimity pass.
        Use mixed senders with low confidence so sender pass also skips."""
        items = [
            _make_classification(1, Tier.REVIEW, 0.50, cluster_id=-1, cluster_label=None),
            _make_classification(2, Tier.REVIEW, 0.50, cluster_id=None, cluster_label=None),
        ]
        sender_lookup = {1: "a@test.com", 2: "b@test.com"}

        result = auto_triage(items, sender_lookup, review_only=False)
        assert result.auto_resolved_count == 0
        assert result.remaining_count == 2

    def test_resolution_has_reason_string(self) -> None:
        items = [
            _make_classification(i, Tier.KEEP_HISTORICAL, 0.92, cluster_id=5, cluster_label="receipts")
            for i in range(1, 4)
        ]
        sender_lookup = {i: "store@shop.com" for i in range(1, 4)}

        result = auto_triage(items, sender_lookup, review_only=False)
        assert len(result.auto_resolved) == 1
        resolution = result.auto_resolved[0]
        assert "cluster" in resolution.reason.lower() or "unanimity" in resolution.reason.lower()
        assert resolution.cluster_label == "receipts"
        assert resolution.avg_confidence > 0.9


class TestSenderConsistency:
    """Pass 2: auto-resolve senders where all emails share same tier + confidence > 0.80."""

    def test_resolves_consistent_sender(self) -> None:
        """Sender with all emails same tier and confidence > 0.80."""
        items = [
            _make_classification(1, Tier.KEEP_HISTORICAL, 0.85, cluster_id=None),
            _make_classification(2, Tier.KEEP_HISTORICAL, 0.82, cluster_id=None),
            _make_classification(3, Tier.KEEP_HISTORICAL, 0.88, cluster_id=None),
        ]
        sender_lookup = {1: "news@corp.com", 2: "news@corp.com", 3: "news@corp.com"}

        result = auto_triage(items, sender_lookup, review_only=False)
        assert result.auto_resolved_count == 3

    def test_skips_inconsistent_sender(self) -> None:
        """Sender with mixed tiers should NOT be auto-resolved."""
        items = [
            _make_classification(1, Tier.TRASH, 0.85, cluster_id=None),
            _make_classification(2, Tier.REVIEW, 0.85, cluster_id=None),
        ]
        sender_lookup = {1: "mixed@test.com", 2: "mixed@test.com"}

        result = auto_triage(items, sender_lookup, review_only=False)
        assert result.auto_resolved_count == 0

    def test_skips_sender_below_threshold(self) -> None:
        """Sender with confidence <= 0.55 should NOT be auto-resolved."""
        items = [
            _make_classification(1, Tier.REVIEW, 0.50, cluster_id=None),
            _make_classification(2, Tier.REVIEW, 0.48, cluster_id=None),
        ]
        sender_lookup = {1: "low@test.com", 2: "low@test.com"}

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_count == 0

    def test_sender_pass_after_cluster_pass(self) -> None:
        """Sender consistency runs on items NOT already resolved by cluster unanimity."""
        items = [
            # These will be resolved by cluster unanimity
            _make_classification(1, Tier.TRASH, 0.90, cluster_id=1, cluster_label="spam"),
            _make_classification(2, Tier.TRASH, 0.92, cluster_id=1, cluster_label="spam"),
            # These remain — same sender, should be resolved by sender consistency
            _make_classification(3, Tier.KEEP_HISTORICAL, 0.85, cluster_id=None),
            _make_classification(4, Tier.KEEP_HISTORICAL, 0.83, cluster_id=None),
        ]
        sender_lookup = {
            1: "spam@junk.com", 2: "spam@junk.com",
            3: "keeper@corp.com", 4: "keeper@corp.com",
        }

        result = auto_triage(items, sender_lookup, review_only=False)
        assert result.auto_resolved_count == 4
        assert result.remaining_count == 0


class TestProtectedSafety:
    """Protected emails must never be auto-resolved to trash."""

    def test_protected_blocks_trash_cluster_resolution(self) -> None:
        """Protected item in cluster prevents cluster unanimity for trash.
        Use same sender so sender pass also sees the protected item."""
        items = [
            _make_classification(1, Tier.TRASH, 0.95, cluster_id=1, cluster_label="spam", protected=True),
            _make_classification(2, Tier.TRASH, 0.95, cluster_id=1, cluster_label="spam"),
        ]
        sender_lookup = {1: "same@test.com", 2: "same@test.com"}

        result = auto_triage(items, sender_lookup, review_only=False)
        # Cluster unanimity skipped (protected item in trash cluster)
        # Sender consistency also skipped (same sender, protected in trash group)
        assert result.auto_resolved_count == 0

    def test_protected_allows_non_trash_resolution(self) -> None:
        items = [
            _make_classification(1, Tier.KEEP_HISTORICAL, 0.92, cluster_id=1, cluster_label="receipts", protected=True),
            _make_classification(2, Tier.KEEP_HISTORICAL, 0.92, cluster_id=1, cluster_label="receipts"),
        ]
        sender_lookup = {1: "store@shop.com", 2: "store@shop.com"}

        result = auto_triage(items, sender_lookup, review_only=False)
        # Non-trash resolution with protected is fine
        assert result.auto_resolved_count == 2


class TestReviewOnlyFilter:
    """Default behavior: only process Review-tier items."""

    def test_review_only_default(self) -> None:
        items = [
            _make_classification(1, Tier.TRASH, 0.95, cluster_id=1, cluster_label="spam"),
            _make_classification(2, Tier.REVIEW, 0.90, cluster_id=2, cluster_label="maybe"),
            _make_classification(3, Tier.REVIEW, 0.90, cluster_id=2, cluster_label="maybe"),
        ]
        sender_lookup = {1: "a@test.com", 2: "b@test.com", 3: "c@test.com"}

        result = auto_triage(items, sender_lookup, review_only=True)
        # Review→review resolution is skipped (same-tier noise), items stay in remaining
        assert result.auto_resolved_count == 0
        assert result.remaining_count == 2

    def test_review_only_false_processes_all(self) -> None:
        items = [
            _make_classification(1, Tier.TRASH, 0.95, cluster_id=1, cluster_label="spam"),
            _make_classification(2, Tier.TRASH, 0.95, cluster_id=1, cluster_label="spam"),
            _make_classification(3, Tier.REVIEW, 0.90, cluster_id=2, cluster_label="maybe"),
            _make_classification(4, Tier.REVIEW, 0.90, cluster_id=2, cluster_label="maybe"),
        ]
        sender_lookup = {i: f"s{i}@test.com" for i in range(1, 5)}

        result = auto_triage(items, sender_lookup, review_only=False)
        assert result.auto_resolved_count == 4


class TestCrossTierSender:
    """Pass 0: auto-resolve review items when sender has consistent non-review classification."""

    def test_resolves_review_items_when_sender_dominant_in_trash(self) -> None:
        """Sender with >75% non-review emails in trash → review emails auto-resolved to trash."""
        items = [
            # Non-review: 4 trash emails from this sender
            _make_classification(1, Tier.TRASH, 0.30, cluster_id=None),
            _make_classification(2, Tier.TRASH, 0.28, cluster_id=None),
            _make_classification(3, Tier.TRASH, 0.32, cluster_id=None),
            _make_classification(4, Tier.TRASH, 0.25, cluster_id=None),
            # Review: 2 emails from the same sender
            _make_classification(5, Tier.REVIEW, 0.55, cluster_id=None),
            _make_classification(6, Tier.REVIEW, 0.52, cluster_id=None),
        ]
        sender_lookup = {i: "spam@junk.com" for i in range(1, 7)}

        result = auto_triage(items, sender_lookup, review_only=True)
        assert result.auto_resolved_count == 2
        assert result.auto_resolved[0].tier == Tier.TRASH
        assert "cross-tier" in result.auto_resolved[0].reason.lower()

    def test_skips_when_insufficient_evidence(self) -> None:
        """Sender with <3 non-review emails should not trigger cross-tier resolution."""
        items = [
            _make_classification(1, Tier.TRASH, 0.30, cluster_id=None),
            _make_classification(2, Tier.TRASH, 0.28, cluster_id=None),
            # Only 2 non-review emails — below threshold of 3
            _make_classification(3, Tier.REVIEW, 0.55, cluster_id=None),
        ]
        sender_lookup = {1: "sparse@test.com", 2: "sparse@test.com", 3: "sparse@test.com"}

        result = auto_triage(items, sender_lookup, review_only=True)
        assert result.auto_resolved_count == 0

    def test_skips_when_sender_split_across_tiers(self) -> None:
        """Sender with emails split evenly across tiers should not be auto-resolved."""
        items = [
            _make_classification(1, Tier.TRASH, 0.30, cluster_id=None),
            _make_classification(2, Tier.TRASH, 0.28, cluster_id=None),
            _make_classification(3, Tier.KEEP_HISTORICAL, 0.70, cluster_id=None),
            _make_classification(4, Tier.KEEP_HISTORICAL, 0.72, cluster_id=None),
            # Review items — sender has 50/50 split, no dominant tier
            _make_classification(5, Tier.REVIEW, 0.55, cluster_id=None),
        ]
        sender_lookup = {i: "split@test.com" for i in range(1, 6)}

        result = auto_triage(items, sender_lookup, review_only=True)
        assert result.auto_resolved_count == 0

    def test_protected_blocks_cross_tier_trash(self) -> None:
        """Protected review items should not be auto-trashed via cross-tier."""
        items = [
            _make_classification(1, Tier.TRASH, 0.30, cluster_id=None),
            _make_classification(2, Tier.TRASH, 0.28, cluster_id=None),
            _make_classification(3, Tier.TRASH, 0.32, cluster_id=None),
            _make_classification(4, Tier.REVIEW, 0.55, cluster_id=None, protected=True),
        ]
        sender_lookup = {i: "sender@test.com" for i in range(1, 5)}

        result = auto_triage(items, sender_lookup, review_only=True)
        assert result.auto_resolved_count == 0

    def test_cross_tier_disabled_when_review_only_false(self) -> None:
        """Cross-tier pass only runs when review_only=True."""
        items = [
            _make_classification(1, Tier.TRASH, 0.30, cluster_id=None),
            _make_classification(2, Tier.TRASH, 0.28, cluster_id=None),
            _make_classification(3, Tier.TRASH, 0.32, cluster_id=None),
            _make_classification(4, Tier.REVIEW, 0.45, cluster_id=None),
        ]
        sender_lookup = {i: "sender@test.com" for i in range(1, 5)}

        # review_only=False processes all items, no cross-tier pass
        result = auto_triage(items, sender_lookup, review_only=False)
        # The review item (conf 0.45) won't match cluster/sender thresholds
        # because it's mixed tiers in one sender group
        cross_tier_resolutions = [r for r in result.auto_resolved if "cross-tier" in r.reason.lower()]
        assert len(cross_tier_resolutions) == 0


class TestAutoTriageResult:
    """Result object provides accurate counts and transparency."""

    def test_counts_match(self) -> None:
        items = [
            _make_classification(i, Tier.REVIEW, 0.90, cluster_id=1, cluster_label="news")
            for i in range(1, 11)
        ] + [
            _make_classification(i, Tier.REVIEW, 0.30)
            for i in range(11, 16)
        ]
        sender_lookup = {i: f"s{i}@test.com" for i in range(1, 16)}

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_count + result.remaining_count == 15
        total_resolved_ids = sum(len(r.message_ids) for r in result.auto_resolved)
        assert total_resolved_ids == result.auto_resolved_count

    def test_empty_input(self) -> None:
        result = auto_triage([], {})
        assert result.auto_resolved_count == 0
        assert result.remaining_count == 0
        assert result.auto_resolved == []
        assert result.remaining == []

    def test_cluster_count_in_result(self) -> None:
        # Use non-review tiers so cluster unanimity resolves them (review→review is skipped)
        items = [
            _make_classification(1, Tier.TRASH, 0.92, cluster_id=1, cluster_label="a"),
            _make_classification(2, Tier.TRASH, 0.92, cluster_id=1, cluster_label="a"),
            _make_classification(3, Tier.KEEP_HISTORICAL, 0.88, cluster_id=2, cluster_label="b"),
            _make_classification(4, Tier.KEEP_HISTORICAL, 0.88, cluster_id=2, cluster_label="b"),
        ]
        sender_lookup = {i: f"s{i}@test.com" for i in range(1, 5)}

        result = auto_triage(items, sender_lookup, review_only=False)
        assert result.auto_resolved_cluster_count == 2
