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

        result = auto_triage(items, sender_lookup)

        assert isinstance(result, AutoTriageResult)
        assert result.auto_resolved_count == 5
        assert result.remaining_count == 0
        assert len(result.auto_resolved) == 1
        assert result.auto_resolved[0].tier == Tier.TRASH

    def test_skips_low_confidence_cluster(self) -> None:
        """Cluster with confidence <= 0.85 should NOT be auto-resolved."""
        items = [
            _make_classification(1, Tier.REVIEW, 0.80, cluster_id=1, cluster_label="maybe"),
            _make_classification(2, Tier.REVIEW, 0.70, cluster_id=1, cluster_label="maybe"),
        ]
        sender_lookup = {1: "a@test.com", 2: "b@test.com"}

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_count == 0
        assert result.remaining_count == 2

    def test_skips_mixed_tier_cluster(self) -> None:
        """Cluster with mixed tiers should NOT be auto-resolved."""
        items = [
            _make_classification(1, Tier.TRASH, 0.90, cluster_id=1, cluster_label="mixed"),
            _make_classification(2, Tier.REVIEW, 0.90, cluster_id=1, cluster_label="mixed"),
        ]
        sender_lookup = {1: "a@test.com", 2: "b@test.com"}

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_count == 0

    def test_skips_noise_cluster(self) -> None:
        """Noise cluster (id=-1 or None) should be skipped."""
        items = [
            _make_classification(1, Tier.TRASH, 0.95, cluster_id=-1, cluster_label=None),
            _make_classification(2, Tier.TRASH, 0.95, cluster_id=None, cluster_label=None),
        ]
        sender_lookup = {1: "a@test.com", 2: "b@test.com"}

        result = auto_triage(items, sender_lookup)
        # Should not be resolved by cluster unanimity (noise skipped)
        # But could be resolved by sender consistency if same sender
        # With different senders: remains unresolved
        assert result.auto_resolved_count == 0

    def test_resolution_has_reason_string(self) -> None:
        items = [
            _make_classification(i, Tier.KEEP_HISTORICAL, 0.92, cluster_id=5, cluster_label="receipts")
            for i in range(1, 4)
        ]
        sender_lookup = {i: "store@shop.com" for i in range(1, 4)}

        result = auto_triage(items, sender_lookup)
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

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_count == 3

    def test_skips_inconsistent_sender(self) -> None:
        """Sender with mixed tiers should NOT be auto-resolved."""
        items = [
            _make_classification(1, Tier.TRASH, 0.85, cluster_id=None),
            _make_classification(2, Tier.REVIEW, 0.85, cluster_id=None),
        ]
        sender_lookup = {1: "mixed@test.com", 2: "mixed@test.com"}

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_count == 0

    def test_skips_sender_below_threshold(self) -> None:
        """Sender with confidence <= 0.80 should NOT be auto-resolved."""
        items = [
            _make_classification(1, Tier.REVIEW, 0.75, cluster_id=None),
            _make_classification(2, Tier.REVIEW, 0.78, cluster_id=None),
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

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_count == 4
        assert result.remaining_count == 0


class TestProtectedSafety:
    """Protected emails must never be auto-resolved to trash."""

    def test_protected_blocks_trash_resolution(self) -> None:
        items = [
            _make_classification(1, Tier.TRASH, 0.95, cluster_id=1, cluster_label="spam", protected=True),
            _make_classification(2, Tier.TRASH, 0.95, cluster_id=1, cluster_label="spam"),
        ]
        sender_lookup = {1: "a@test.com", 2: "b@test.com"}

        result = auto_triage(items, sender_lookup)
        # Entire cluster should be skipped because one item is protected
        assert result.auto_resolved_count == 0

    def test_protected_allows_non_trash_resolution(self) -> None:
        items = [
            _make_classification(1, Tier.KEEP_HISTORICAL, 0.92, cluster_id=1, cluster_label="receipts", protected=True),
            _make_classification(2, Tier.KEEP_HISTORICAL, 0.92, cluster_id=1, cluster_label="receipts"),
        ]
        sender_lookup = {1: "store@shop.com", 2: "store@shop.com"}

        result = auto_triage(items, sender_lookup)
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
        # Only review items processed; trash item excluded from input
        assert result.auto_resolved_count == 2
        assert result.remaining_count == 0

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
        items = [
            _make_classification(1, Tier.REVIEW, 0.92, cluster_id=1, cluster_label="a"),
            _make_classification(2, Tier.REVIEW, 0.92, cluster_id=1, cluster_label="a"),
            _make_classification(3, Tier.REVIEW, 0.88, cluster_id=2, cluster_label="b"),
            _make_classification(4, Tier.REVIEW, 0.88, cluster_id=2, cluster_label="b"),
        ]
        sender_lookup = {i: f"s{i}@test.com" for i in range(1, 5)}

        result = auto_triage(items, sender_lookup)
        assert result.auto_resolved_cluster_count == 2
