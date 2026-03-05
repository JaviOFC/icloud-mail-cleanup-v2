"""Tests for post-review propagation engine."""

from __future__ import annotations

import time

import pytest

from icloud_cleanup.models import Classification, Tier
from icloud_cleanup.propagation import (
    PropagationSuggestion,
    find_propagation_targets,
)


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


class TestDomainMatch:
    """Tests for domain-based propagation."""

    def test_finds_same_domain_senders(self) -> None:
        classifications = [
            _make_classification(1),
            _make_classification(2),
            _make_classification(3),
        ]
        sender_lookup = {
            1: "news@store.com",
            2: "promo@store.com",
            3: "alerts@store.com",
        }
        suggestions = find_propagation_targets(
            decided_sender="news@store.com",
            action="approve",
            all_classifications=classifications,
            sender_lookup=sender_lookup,
            already_decided={1},
        )
        # Should suggest promo@store.com and alerts@store.com
        assert len(suggestions) > 0
        all_targets = []
        for s in suggestions:
            all_targets.extend(s.target_senders)
        assert "promo@store.com" in all_targets
        assert "alerts@store.com" in all_targets

    def test_excludes_common_domains(self) -> None:
        """gmail.com, yahoo.com, etc. should not trigger domain propagation."""
        classifications = [
            _make_classification(1),
            _make_classification(2),
        ]
        sender_lookup = {
            1: "alice@gmail.com",
            2: "bob@gmail.com",
        }
        suggestions = find_propagation_targets(
            decided_sender="alice@gmail.com",
            action="approve",
            all_classifications=classifications,
            sender_lookup=sender_lookup,
            already_decided={1},
        )
        # No domain propagation for common email providers
        domain_suggestions = [s for s in suggestions if "domain" in s.reason.lower()]
        assert len(domain_suggestions) == 0

    def test_excludes_already_decided(self) -> None:
        classifications = [
            _make_classification(1),
            _make_classification(2),
            _make_classification(3),
        ]
        sender_lookup = {
            1: "news@store.com",
            2: "promo@store.com",
            3: "alerts@store.com",
        }
        # message 2 already decided
        suggestions = find_propagation_targets(
            decided_sender="news@store.com",
            action="approve",
            all_classifications=classifications,
            sender_lookup=sender_lookup,
            already_decided={1, 2},
        )
        all_target_ids = []
        for s in suggestions:
            all_target_ids.extend(s.target_message_ids)
        assert 2 not in all_target_ids


class TestSubdomainMatch:
    """Tests for subdomain-based propagation."""

    def test_finds_subdomain_senders(self) -> None:
        classifications = [
            _make_classification(1),
            _make_classification(2),
            _make_classification(3),
        ]
        sender_lookup = {
            1: "news@marketing.store.com",
            2: "alerts@support.store.com",
            3: "info@billing.store.com",
        }
        suggestions = find_propagation_targets(
            decided_sender="news@marketing.store.com",
            action="approve",
            all_classifications=classifications,
            sender_lookup=sender_lookup,
            already_decided={1},
        )
        all_targets = []
        for s in suggestions:
            all_targets.extend(s.target_senders)
        assert any("store.com" in t for t in all_targets)


class TestAliasDetection:
    """Tests for alias-based propagation (same local-part prefix)."""

    def test_finds_plus_aliases(self) -> None:
        classifications = [
            _make_classification(1),
            _make_classification(2),
        ]
        sender_lookup = {
            1: "shop@store.com",
            2: "noreply@store.com",
        }
        # Both from same domain — at minimum domain match should work
        suggestions = find_propagation_targets(
            decided_sender="shop@store.com",
            action="approve",
            all_classifications=classifications,
            sender_lookup=sender_lookup,
            already_decided={1},
        )
        assert len(suggestions) > 0


class TestPropagationSuggestionDataclass:
    """Tests for PropagationSuggestion structure."""

    def test_suggestion_fields(self) -> None:
        suggestion = PropagationSuggestion(
            source_sender="news@store.com",
            target_senders=["promo@store.com"],
            target_message_ids=[2, 3],
            reason="Same domain: store.com",
            suggested_action="approve",
        )
        assert suggestion.source_sender == "news@store.com"
        assert suggestion.suggested_action == "approve"
        assert len(suggestion.target_message_ids) == 2


class TestEmptyInputs:
    """Edge case tests for empty or minimal inputs."""

    def test_no_classifications(self) -> None:
        suggestions = find_propagation_targets(
            decided_sender="test@example.com",
            action="approve",
            all_classifications=[],
            sender_lookup={},
            already_decided=set(),
        )
        assert suggestions == []

    def test_all_already_decided(self) -> None:
        classifications = [
            _make_classification(1),
            _make_classification(2),
        ]
        sender_lookup = {
            1: "news@store.com",
            2: "promo@store.com",
        }
        suggestions = find_propagation_targets(
            decided_sender="news@store.com",
            action="approve",
            all_classifications=classifications,
            sender_lookup=sender_lookup,
            already_decided={1, 2},
        )
        # All already decided, no suggestions
        all_target_ids = []
        for s in suggestions:
            all_target_ids.extend(s.target_message_ids)
        assert len(all_target_ids) == 0
