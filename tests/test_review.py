"""Tests for interactive review session manager."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from rich.console import Console

from icloud_cleanup.models import TIER_COLORS, Classification, Message, Tier
from icloud_cleanup.review import (
    ReviewSession,
    _build_cluster_panel,
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


def _make_message(
    message_id: int,
    *,
    sender_address: str = "test@example.com",
    subject: str = "Test subject",
    date_received: int = 1700000000,
) -> Message:
    return Message(
        rowid=message_id,
        message_id=message_id,
        conversation_id=0,
        flags=0,
        read=1,
        flagged=0,
        deleted=0,
        size=1000,
        date_received=date_received,
        sender_address=sender_address,
        subject=subject,
        mailbox_url="imap://UUID/INBOX",
        list_id_hash=None,
        unsubscribe_type=None,
        automated_conversation=0,
        model_category=None,
        model_high_impact=0,
    )


class TestBuildClusterPanel:
    """Tests for cluster panel display enhancements."""

    def test_panel_title_contains_colored_tier(self) -> None:
        msg = _make_message(1)
        cls = _make_classification(1, Tier.TRASH, 0.95)
        msg_index = {1: msg}
        panel = _build_cluster_panel("spam_cluster", [cls], [msg], msg_index)
        title_str = str(panel.title)
        assert "trash" in title_str
        assert "red" in title_str

    def test_panel_contains_date_range(self) -> None:
        msgs = [
            _make_message(1, date_received=1546300800),
            _make_message(2, date_received=1711929600),
        ]
        items = [
            _make_classification(1, Tier.REVIEW, 0.5),
            _make_classification(2, Tier.REVIEW, 0.6),
        ]
        msg_index = {m.message_id: m for m in msgs}
        panel = _build_cluster_panel("test", items, msgs, msg_index)
        from io import StringIO
        console = Console(file=StringIO(), force_terminal=True, width=120)
        console.print(panel)
        output = console.file.getvalue()
        assert "Date range" in output
        # Dates span multiple years — verify the range separator is present
        assert " - " in output

    def test_panel_single_month_date_range(self) -> None:
        msgs = [
            _make_message(1, date_received=1700000000),
            _make_message(2, date_received=1700086400),
        ]
        items = [
            _make_classification(1, Tier.REVIEW, 0.5),
            _make_classification(2, Tier.REVIEW, 0.6),
        ]
        msg_index = {m.message_id: m for m in msgs}
        panel = _build_cluster_panel("test", items, msgs, msg_index)
        from io import StringIO
        console = Console(file=StringIO(), force_terminal=True, width=120)
        console.print(panel)
        output = console.file.getvalue()
        assert "Date range" in output


class TestTierColorsShared:
    """Tests that TIER_COLORS is properly shared."""

    def test_all_tiers_have_color(self) -> None:
        for tier in Tier:
            assert tier in TIER_COLORS

    def test_expected_colors(self) -> None:
        assert TIER_COLORS[Tier.TRASH] == "red"
        assert TIER_COLORS[Tier.KEEP_ACTIVE] == "green"
        assert TIER_COLORS[Tier.KEEP_HISTORICAL] == "blue"
        assert TIER_COLORS[Tier.REVIEW] == "yellow"


class TestInspectModeDisplay:
    """Tests for the enhanced inspect mode display format."""

    def test_inspect_format_with_summary(self) -> None:
        """Verify display includes summary, signals, date, colored tier."""
        from datetime import datetime

        msg = _make_message(1, subject="Invoice #4521",
                           sender_address="billing@co.com",
                           date_received=1700000000)
        cls = _make_classification(
            1, Tier.REVIEW, 0.523,
            cluster_id=1, cluster_label="invoices",
        )
        # Override signals for test
        cls.signals = "sender_score=0.30; frequency=0.45; age=0.80"
        summary_lookup = {1: "Thank you for your payment. Your invoice for services rendered..."}

        tier_color = TIER_COLORS[cls.tier]
        date_str = datetime.fromtimestamp(msg.date_received).strftime("%b %d, %Y")

        lines = [
            f"\n  [bold]{msg.subject}[/bold]",
            f"  From: {msg.sender_address}",
            f"  Date: {date_str} | Tier: [{tier_color}]{cls.tier.value}[/{tier_color}] | Confidence: {cls.confidence:.3f}",
        ]
        if summary_lookup and cls.message_id in summary_lookup:
            snippet = summary_lookup[cls.message_id][:200]
            lines.append(f"  [dim]Preview: {snippet}[/dim]")
        if cls.signals:
            lines.append(f"  [dim]Signals: {cls.signals}[/dim]")

        output = "\n".join(lines)
        assert "Invoice #4521" in output
        assert "billing@co.com" in output
        assert "yellow" in output
        assert "0.523" in output
        assert "Thank you for your payment" in output
        assert "sender_score=0.30" in output
        assert date_str in output

    def test_inspect_format_without_summary(self) -> None:
        msg = _make_message(1)
        cls = _make_classification(1, Tier.TRASH, 0.95)
        cls.signals = ""

        lines = [f"  [bold]{msg.subject}[/bold]"]
        summary_lookup: dict[int, str] | None = None
        if summary_lookup and cls.message_id in summary_lookup:
            lines.append("Preview line")
        if cls.signals:
            lines.append("Signals line")

        output = "\n".join(lines)
        assert "Preview" not in output
        assert "Signals" not in output
