"""Tests for interactive review session manager."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from icloud_cleanup.models import Classification, Message, Tier
from icloud_cleanup.review import (
    ReviewSession,
    get_session_path,
    load_session,
    save_session,
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


class TestReviewSession:
    """Tests for ReviewSession dataclass."""

    def test_default_fields(self) -> None:
        session = ReviewSession(
            session_id="test_001",
            started_at=1700000000,
            last_updated=1700000000,
        )
        assert session.session_id == "test_001"
        assert session.version == 1
        assert session.decisions == {}
        assert session.individual_decisions == {}
        assert session.propagation_applied == []
        assert session.completed is False
        assert session.auto_triage_summary is None

    def test_stores_decisions(self) -> None:
        session = ReviewSession(
            session_id="test_002",
            started_at=1700000000,
            last_updated=1700000000,
            decisions={
                "newsletters": {"action": "approve", "timestamp": 1700000100},
            },
        )
        assert "newsletters" in session.decisions
        assert session.decisions["newsletters"]["action"] == "approve"


class TestSaveLoadSession:
    """Tests for session persistence roundtrip."""

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        session_path = tmp_path / "session.json"
        original = ReviewSession(
            session_id="roundtrip_001",
            started_at=1700000000,
            last_updated=1700000000,
            decisions={
                "newsletters": {"action": "approve", "timestamp": 1700000100},
                "social_alerts": {"action": "skip", "timestamp": 1700000200},
            },
            individual_decisions={
                "12345": {"action": "approve", "timestamp": 1700000300},
            },
            propagation_applied=[
                {"source": "news@store.com", "targets": ["promo@store.com"]},
            ],
        )

        save_session(original, session_path)
        loaded = load_session(session_path)

        assert loaded is not None
        assert loaded.session_id == original.session_id
        assert loaded.decisions == original.decisions
        assert loaded.individual_decisions == original.individual_decisions
        assert loaded.propagation_applied == original.propagation_applied
        assert loaded.completed == original.completed

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        result = load_session(tmp_path / "does_not_exist.json")
        assert result is None

    def test_save_updates_last_updated(self, tmp_path: Path) -> None:
        session_path = tmp_path / "session.json"
        session = ReviewSession(
            session_id="ts_test",
            started_at=1700000000,
            last_updated=1700000000,
        )
        save_session(session, session_path)
        loaded = load_session(session_path)
        assert loaded is not None
        assert loaded.last_updated >= session.started_at

    def test_atomic_write_creates_file(self, tmp_path: Path) -> None:
        session_path = tmp_path / "atomic.json"
        session = ReviewSession(
            session_id="atomic_001",
            started_at=1700000000,
            last_updated=1700000000,
        )
        save_session(session, session_path)
        assert session_path.exists()
        # No leftover .tmp file
        assert not (tmp_path / "atomic.json.tmp").exists()

    def test_save_preserves_completed_flag(self, tmp_path: Path) -> None:
        session_path = tmp_path / "completed.json"
        session = ReviewSession(
            session_id="done_001",
            started_at=1700000000,
            last_updated=1700000000,
            completed=True,
        )
        save_session(session, session_path)
        loaded = load_session(session_path)
        assert loaded is not None
        assert loaded.completed is True


class TestSessionResume:
    """Tests for review session resume behavior."""

    def test_decided_clusters_tracked(self) -> None:
        session = ReviewSession(
            session_id="resume_001",
            started_at=1700000000,
            last_updated=1700000000,
            decisions={
                "newsletters": {"action": "approve", "timestamp": 1700000100},
                "social_alerts": {"action": "skip", "timestamp": 1700000200},
            },
        )
        # The session should know which clusters have been decided
        assert "newsletters" in session.decisions
        assert "social_alerts" in session.decisions
        assert "unseen_cluster" not in session.decisions


class TestTrashAutoApprove:
    """Tests for auto-approve threshold logic."""

    def test_high_confidence_trash_auto_approvable(self) -> None:
        """Trash items with confidence > 0.98 should be auto-approvable."""
        from icloud_cleanup.review import is_auto_approvable

        classifications = [
            _make_classification(1, Tier.TRASH, 0.99, cluster_id=1, cluster_label="spam"),
            _make_classification(2, Tier.TRASH, 0.985, cluster_id=1, cluster_label="spam"),
        ]
        assert is_auto_approvable(classifications) is True

    def test_borderline_trash_not_auto_approvable(self) -> None:
        """Trash items with confidence 0.95-0.98 need human review."""
        from icloud_cleanup.review import is_auto_approvable

        classifications = [
            _make_classification(1, Tier.TRASH, 0.97, cluster_id=1, cluster_label="spam"),
            _make_classification(2, Tier.TRASH, 0.96, cluster_id=1, cluster_label="spam"),
        ]
        assert is_auto_approvable(classifications) is False

    def test_non_trash_not_auto_approvable(self) -> None:
        """Non-trash items should never be auto-approved."""
        from icloud_cleanup.review import is_auto_approvable

        classifications = [
            _make_classification(1, Tier.REVIEW, 0.99, cluster_id=1, cluster_label="misc"),
        ]
        assert is_auto_approvable(classifications) is False

    def test_mixed_confidence_not_auto_approvable(self) -> None:
        """Cluster with mixed confidence should not be auto-approved."""
        from icloud_cleanup.review import is_auto_approvable

        classifications = [
            _make_classification(1, Tier.TRASH, 0.99, cluster_id=1, cluster_label="spam"),
            _make_classification(2, Tier.TRASH, 0.90, cluster_id=1, cluster_label="spam"),
        ]
        assert is_auto_approvable(classifications) is False


class TestGetSessionPath:
    """Tests for default session path."""

    def test_returns_path_in_home_dir(self) -> None:
        path = get_session_path()
        assert path.name == "review_session.json"
        assert ".icloud-cleanup" in str(path)
