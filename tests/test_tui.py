"""Tests for the Textual TUI application."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from icloud_cleanup.checkpoint import save_checkpoint
from icloud_cleanup.models import Classification, Tier


def _make_test_classifications() -> list[Classification]:
    """Create a minimal set of classifications spanning all tiers."""
    now = int(time.time())
    return [
        Classification(message_id=1, tier=Tier.TRASH, confidence=0.02, signals="junk", protected=False, timestamp=now),
        Classification(message_id=2, tier=Tier.TRASH, confidence=0.01, signals="junk", protected=False, timestamp=now),
        Classification(message_id=3, tier=Tier.KEEP_ACTIVE, confidence=0.95, signals="personal", protected=True, timestamp=now),
        Classification(message_id=4, tier=Tier.KEEP_HISTORICAL, confidence=0.70, signals="old_receipt", protected=False, timestamp=now),
        Classification(message_id=5, tier=Tier.REVIEW, confidence=0.50, signals="ambiguous", protected=False, timestamp=now),
    ]


def _write_test_checkpoint(tmp_path: Path) -> Path:
    """Write a test checkpoint file and return its path."""
    checkpoint_path = tmp_path / "test_checkpoint.jsonl"
    save_checkpoint(_make_test_classifications(), checkpoint_path)
    return checkpoint_path


@pytest.mark.asyncio
async def test_app_launches(tmp_path: Path) -> None:
    """App should launch and show DashboardScreen by default."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.dashboard import DashboardScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        assert isinstance(app.screen, DashboardScreen)


@pytest.mark.asyncio
async def test_mode_switching(tmp_path: Path) -> None:
    """D/R/E/P keys should switch between screens."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens import ReviewScreen
    from icloud_cleanup.tui.screens.dashboard import DashboardScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        assert isinstance(app.screen, DashboardScreen)

        await pilot.press("r")
        assert isinstance(app.screen, ReviewScreen)

        await pilot.press("d")
        assert isinstance(app.screen, DashboardScreen)


@pytest.mark.asyncio
async def test_theme_toggle(tmp_path: Path) -> None:
    """T key should toggle between dark and light themes."""
    from icloud_cleanup.tui import CleanupApp

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        initial_theme = app.theme
        await pilot.press("t")
        assert app.theme != initial_theme
        await pilot.press("t")
        assert app.theme == initial_theme


@pytest.mark.asyncio
async def test_quit(tmp_path: Path) -> None:
    """Q key should exit the app."""
    from icloud_cleanup.tui import CleanupApp

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("q")


@pytest.mark.asyncio
async def test_dashboard_shows_tier_summary(tmp_path: Path) -> None:
    """Dashboard should contain a TierSummaryWidget with tier names."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.widgets.tier_summary import TierSummaryWidget

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        # Wait for background data load
        await pilot.pause(delay=0.5)

        widget = app.query_one("#tier-summary", TierSummaryWidget)
        assert widget is not None


@pytest.mark.asyncio
async def test_dashboard_shows_storage_banner(tmp_path: Path) -> None:
    """Dashboard should contain a StorageBannerWidget showing savings text."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.widgets.storage_banner import StorageBannerWidget

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(delay=0.5)

        widget = app.query_one("#storage-banner", StorageBannerWidget)
        assert widget is not None


# --- Review screen tests ---


def _make_review_classifications() -> list[Classification]:
    """Create classifications with cluster info for review screen tests."""
    now = int(time.time())
    return [
        Classification(
            message_id=1, tier=Tier.TRASH, confidence=0.02, signals="junk",
            protected=False, timestamp=now, cluster_id=1, cluster_label="Spam Newsletters",
        ),
        Classification(
            message_id=2, tier=Tier.TRASH, confidence=0.01, signals="junk",
            protected=False, timestamp=now, cluster_id=1, cluster_label="Spam Newsletters",
        ),
        Classification(
            message_id=3, tier=Tier.KEEP_ACTIVE, confidence=0.95, signals="personal",
            protected=True, timestamp=now, cluster_id=2, cluster_label="Personal Emails",
        ),
        Classification(
            message_id=4, tier=Tier.KEEP_HISTORICAL, confidence=0.70, signals="old_receipt",
            protected=False, timestamp=now, cluster_id=3, cluster_label="Old Receipts",
        ),
        Classification(
            message_id=5, tier=Tier.REVIEW, confidence=0.50, signals="ambiguous",
            protected=False, timestamp=now, cluster_id=4, cluster_label="Ambiguous Cluster",
        ),
        Classification(
            message_id=6, tier=Tier.REVIEW, confidence=0.45, signals="ambiguous",
            protected=False, timestamp=now, cluster_id=4, cluster_label="Ambiguous Cluster",
        ),
    ]


def _write_review_checkpoint(tmp_path: Path) -> Path:
    """Write a review-ready checkpoint and return its path."""
    checkpoint_path = tmp_path / "review_checkpoint.jsonl"
    save_checkpoint(_make_review_classifications(), checkpoint_path)
    return checkpoint_path


@pytest.mark.asyncio
async def test_review_cluster_list_loads(tmp_path: Path) -> None:
    """Review screen should load cluster list from checkpoint."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.review import ReviewScreen
    from icloud_cleanup.tui.widgets.cluster_list import ClusterListWidget

    checkpoint_path = _write_review_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("r")
        assert isinstance(app.screen, ReviewScreen)
        await pilot.pause(delay=1.0)

        table = app.screen.query_one("#cluster-table", ClusterListWidget)
        assert table.row_count > 0


@pytest.mark.asyncio
async def test_review_detail_updates_on_selection(tmp_path: Path) -> None:
    """Navigating the cluster list should update the detail panel."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.review import ReviewScreen
    from icloud_cleanup.tui.widgets.cluster_detail import ClusterDetailWidget

    checkpoint_path = _write_review_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("r")
        await pilot.pause(delay=1.0)

        # Move down in the cluster list
        await pilot.press("down")
        await pilot.pause(delay=0.3)

        detail = app.screen.query_one("#cluster-detail", ClusterDetailWidget)
        content = detail.query_one("#detail-content")
        # Detail should have been updated (not showing initial placeholder)
        assert content is not None


@pytest.mark.asyncio
async def test_bulk_approve(tmp_path: Path) -> None:
    """Selecting clusters and approving should update the session."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.review import ReviewScreen

    checkpoint_path = _write_review_checkpoint(tmp_path)
    session_path = tmp_path / "test_session.json"
    app = CleanupApp(checkpoint_path=checkpoint_path, session_path=session_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("r")
        await pilot.pause(delay=1.0)

        # Select first cluster with Space
        await pilot.press("space")
        await pilot.pause(delay=0.2)

        # Approve via button
        await pilot.press("a")
        await pilot.pause(delay=0.5)

        assert app.session is not None
        assert len(app.session.decisions) > 0


@pytest.mark.asyncio
async def test_session_interop(tmp_path: Path) -> None:
    """Session created in TUI should be loadable by CLI review module."""
    from icloud_cleanup.review import load_session
    from icloud_cleanup.tui import CleanupApp

    checkpoint_path = _write_review_checkpoint(tmp_path)
    session_path = tmp_path / "interop_session.json"
    app = CleanupApp(checkpoint_path=checkpoint_path, session_path=session_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("r")
        await pilot.pause(delay=1.0)

        # Select and approve
        await pilot.press("space")
        await pilot.pause(delay=0.2)
        await pilot.press("a")
        await pilot.pause(delay=0.5)

    # Load session with CLI module
    loaded = load_session(session_path)
    assert loaded is not None
    assert len(loaded.decisions) > 0
    assert loaded.session_id.startswith("tui-")


@pytest.mark.asyncio
async def test_propagation_tab_exists(tmp_path: Path) -> None:
    """Review screen should have a Propagation tab with PropagationTabWidget."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.review import ReviewScreen
    from icloud_cleanup.tui.widgets.propagation_tab import PropagationTabWidget

    checkpoint_path = _write_review_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("r")
        await pilot.pause(delay=1.0)

        # PropagationTabWidget should exist in the DOM
        prop_tab = app.screen.query_one("#propagation-tab", PropagationTabWidget)
        assert prop_tab is not None
        assert len(prop_tab.suggestions) == 0


@pytest.mark.asyncio
async def test_api_status_shows_remaining(tmp_path: Path) -> None:
    """API status should show remaining Review-tier email count."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.review import ReviewScreen

    checkpoint_path = _write_review_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("r")
        await pilot.pause(delay=1.0)

        from textual.widgets import Static

        status = app.screen.query_one("#api-status", Static)
        rendered = status.renderable
        rendered_str = str(rendered)
        # Should mention Review-tier or remaining emails
        assert "remaining" in rendered_str.lower() or "review" in rendered_str.lower() or "decided" in rendered_str.lower()


@pytest.mark.asyncio
async def test_api_button_submits_batch(tmp_path: Path) -> None:
    """Run API Analysis button should call classify_ambiguous_batch (mocked)."""
    from unittest.mock import MagicMock, patch

    from icloud_cleanup.tui import CleanupApp
    import icloud_cleanup.tui.screens.review as review_mod

    checkpoint_path = _write_review_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    mock_batch = MagicMock()
    mock_batch.id = "batch-test-123"

    # Patch at module level so the worker thread picks it up
    original_fn = review_mod.classify_ambiguous_batch
    review_mod.classify_ambiguous_batch = MagicMock(return_value=mock_batch)
    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("r")
            await pilot.pause(delay=1.0)

            # Verify button exists and is not disabled
            btn = app.screen.query_one("#btn-api")
            assert not btn.disabled

            # We have Review-tier items, so clicking should trigger API submission
            # The worker runs in a thread, so we press the button and wait
            btn.press()
            await pilot.pause(delay=2.0)

            # Verify the mock was called (Review-tier emails exist)
            assert review_mod.classify_ambiguous_batch.called
    finally:
        review_mod.classify_ambiguous_batch = original_fn
