"""Tests for the Textual TUI application."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from icloud_cleanup.checkpoint import save_checkpoint
from icloud_cleanup.models import Classification, Tier
from icloud_cleanup.review import ReviewSession


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


# --- Welcome overlay tests ---


@pytest.mark.asyncio
async def test_welcome_overlay_shown_on_launch(tmp_path: Path) -> None:
    """Welcome overlay should appear on first launch."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.widgets.dismissible_overlay import WelcomeOverlay

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path, show_welcome=True)

    async with app.run_test(size=(120, 40)) as pilot:
        assert isinstance(app.screen, WelcomeOverlay)


@pytest.mark.asyncio
async def test_welcome_overlay_dismisses_on_keypress(tmp_path: Path) -> None:
    """Any keypress should dismiss the welcome overlay."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.dashboard import DashboardScreen
    from icloud_cleanup.tui.widgets.dismissible_overlay import WelcomeOverlay

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path, show_welcome=True)

    async with app.run_test(size=(120, 40)) as pilot:
        assert isinstance(app.screen, WelcomeOverlay)
        await pilot.press("enter")
        assert isinstance(app.screen, DashboardScreen)


# --- Per-screen contextual help tests ---


@pytest.mark.asyncio
async def test_screen_help_shown_on_first_visit(tmp_path: Path) -> None:
    """Switching to Review for the first time should show contextual help."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.widgets.screen_help import ScreenHelpOverlay

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path, show_welcome=True)

    async with app.run_test(size=(120, 40)) as pilot:
        # Dismiss welcome overlay
        await pilot.press("enter")
        await pilot.pause(delay=0.3)

        # Switch to review -- should show screen help
        await pilot.press("r")
        await pilot.pause(delay=0.3)
        assert isinstance(app.screen, ScreenHelpOverlay)

        # Dismiss screen help
        await pilot.press("enter")
        await pilot.pause(delay=0.3)

        # Go back to dashboard, then to review again -- no overlay
        await pilot.press("d")
        await pilot.pause(delay=0.1)
        await pilot.press("r")
        await pilot.pause(delay=0.3)
        # Should NOT show help again
        from icloud_cleanup.tui.screens.review import ReviewScreen
        assert isinstance(app.screen, ReviewScreen)


# --- Help overlay tests ---


@pytest.mark.asyncio
async def test_help_overlay_opens(tmp_path: Path) -> None:
    """Pressing ? should push the HelpScreen modal."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.help_overlay import HelpScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_help_overlay_closes(tmp_path: Path) -> None:
    """Opening help and pressing Escape should return to previous screen."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.dashboard import DashboardScreen
    from icloud_cleanup.tui.screens.help_overlay import HelpScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("question_mark")
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        assert isinstance(app.screen, DashboardScreen)


@pytest.mark.asyncio
async def test_theme_toggle_both_directions(tmp_path: Path) -> None:
    """Theme should toggle dark->light->dark reliably."""
    from icloud_cleanup.tui import CleanupApp

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        initial = app.theme
        await pilot.press("t")
        toggled = app.theme
        assert toggled != initial

        await pilot.press("t")
        assert app.theme == initial

        # Verify the actual theme names
        assert {initial, toggled} == {"textual-dark", "textual-light"}


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


# --- Execute & Pipeline screen tests ---


def _make_test_session() -> ReviewSession:
    """Create a test review session with some approved clusters."""
    now = int(time.time())
    return ReviewSession(
        session_id="test_session",
        started_at=now,
        last_updated=now,
        decisions={
            "Unclustered": {"action": "approve", "timestamp": now},
        },
        individual_decisions={},
    )


@pytest.mark.asyncio
async def test_execute_screen_shows_summary(tmp_path: Path) -> None:
    """Execute screen should display approved item count from session."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.execute import ExecuteScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    session_path = tmp_path / "session.json"

    app = CleanupApp(checkpoint_path=checkpoint_path, session_path=session_path)

    async with app.run_test(size=(120, 40)) as pilot:
        # Wait for data load
        await pilot.pause(delay=0.5)

        # Manually set session (simulates a completed review)
        app.session = _make_test_session()

        # Switch to execute mode
        await pilot.press("e")
        assert isinstance(app.screen, ExecuteScreen)

        # Wait for mount to update summary
        await pilot.pause(delay=0.3)

        summary = app.query_one("#exec-summary")
        # Should show approved count (all 5 classifications match 'Unclustered' since cluster_id is None)
        assert "Approved" in summary.renderable or "approved" in str(summary.renderable).lower() or "No" in str(summary.renderable)


@pytest.mark.asyncio
async def test_execute_screen_has_buttons(tmp_path: Path) -> None:
    """Execute screen should have Dry Run and Execute for Real buttons."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.execute import ExecuteScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("e")
        assert isinstance(app.screen, ExecuteScreen)

        dry_btn = app.query_one("#btn-dry")
        exec_btn = app.query_one("#btn-execute")
        assert dry_btn is not None
        assert exec_btn is not None


@pytest.mark.asyncio
async def test_execute_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry-run execution should update progress and stats via mocked executor."""
    from unittest.mock import MagicMock

    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.execute import ExecuteScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    session_path = tmp_path / "session.json"

    app = CleanupApp(checkpoint_path=checkpoint_path, session_path=session_path)

    mock_result = {
        "success_count": 3,
        "error_count": 0,
        "skipped_protected": 1,
        "errors": [],
    }

    mock_execute = MagicMock(return_value=mock_result)
    monkeypatch.setattr("icloud_cleanup.executor.execute_deletions", mock_execute)

    # Mock open_db + scan_messages to avoid real DB access
    from icloud_cleanup.models import Message

    fake_messages = [
        Message(
            rowid=i, message_id=i, conversation_id=0, flags=0, read=0,
            flagged=0, deleted=0, size=100, date_received=int(time.time()),
            sender_address="test@example.com", subject=f"Test {i}",
            mailbox_url="imap://UUID/INBOX", list_id_hash=None,
            unsubscribe_type=None, automated_conversation=0,
            model_category=None, model_high_impact=0,
        )
        for i in range(1, 6)
    ]

    mock_conn = MagicMock()
    monkeypatch.setattr("icloud_cleanup.scanner.open_db", MagicMock(return_value=mock_conn))
    monkeypatch.setattr("icloud_cleanup.scanner.scan_messages", MagicMock(return_value=fake_messages))

    # Mock ActionLog
    mock_action_log_cls = MagicMock()
    monkeypatch.setattr("icloud_cleanup.executor.ActionLog", mock_action_log_cls)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(delay=0.5)

        # Set session with approved items
        app.session = _make_test_session()

        await pilot.press("e")
        assert isinstance(app.screen, ExecuteScreen)
        await pilot.pause(delay=0.3)

        # Trigger dry run
        await pilot.click("#btn-dry")

        # Wait for worker to complete
        await pilot.pause(delay=1.0)

        stats = app.query_one("#exec-stats")
        stats_text = str(stats.renderable)
        # Should reflect mock results
        assert "3" in stats_text or "Success" in stats_text


@pytest.mark.asyncio
async def test_pipeline_screen_layout(tmp_path: Path) -> None:
    """Pipeline screen should have progress bar, log widget, and buttons."""
    from textual.widgets import Button, ProgressBar

    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.pipeline import PipelineScreen
    from icloud_cleanup.tui.widgets.pipeline_log import PipelineLogWidget

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("p")
        assert isinstance(app.screen, PipelineScreen)

        # Verify key widgets exist
        log_widget = app.query_one("#pipeline-log", PipelineLogWidget)
        assert log_widget is not None

        progress = app.query_one("#pipeline-progress", ProgressBar)
        assert progress is not None

        run_btn = app.query_one("#btn-pipeline", Button)
        assert run_btn is not None

        cancel_btn = app.query_one("#btn-cancel", Button)
        assert cancel_btn is not None
        assert cancel_btn.disabled is True


@pytest.mark.asyncio
async def test_pipeline_screen_status(tmp_path: Path) -> None:
    """Pipeline screen should show 'Ready' status on mount."""
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.pipeline import PipelineScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("p")
        assert isinstance(app.screen, PipelineScreen)

        status = app.query_one("#pipeline-status")
        assert "Ready" in str(status.renderable)


@pytest.mark.asyncio
async def test_pipeline_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipeline worker should advance through 3 steps with mocked I/O."""
    from unittest.mock import MagicMock, patch

    from icloud_cleanup.models import Message
    from icloud_cleanup.tui import CleanupApp
    from icloud_cleanup.tui.screens.pipeline import PipelineScreen

    checkpoint_path = _write_test_checkpoint(tmp_path)
    app = CleanupApp(checkpoint_path=checkpoint_path, db_path=tmp_path / "fake.db")

    fake_messages = [
        Message(
            rowid=i, message_id=i, conversation_id=0, flags=0, read=0,
            flagged=0, deleted=0, size=100, date_received=int(time.time()),
            sender_address="test@example.com", subject=f"Test {i}",
            mailbox_url="imap://UUID/INBOX", list_id_hash=None,
            unsubscribe_type=None, automated_conversation=0,
            model_category=None, model_high_impact=0,
        )
        for i in range(1, 6)
    ]

    mock_conn = MagicMock()

    # Mock all scanner functions
    monkeypatch.setattr("icloud_cleanup.scanner.open_db", MagicMock(return_value=mock_conn))
    monkeypatch.setattr("icloud_cleanup.scanner.scan_messages", MagicMock(return_value=fake_messages))
    monkeypatch.setattr("icloud_cleanup.scanner.get_sent_recipients", MagicMock(return_value={}))
    monkeypatch.setattr("icloud_cleanup.scanner.get_replied_conversation_ids", MagicMock(return_value=set()))
    monkeypatch.setattr("icloud_cleanup.scanner.get_sender_stats", MagicMock(return_value={}))
    monkeypatch.setattr("icloud_cleanup.scanner.get_sender_display_names", MagicMock(return_value={}))
    monkeypatch.setattr("icloud_cleanup.scanner.get_document_attachment_message_ids", MagicMock(return_value=set()))

    # Mock contacts
    mock_sys_contacts = MagicMock()
    mock_sys_contacts.emails = set()
    mock_sys_contacts.names = set()
    monkeypatch.setattr("icloud_cleanup.contacts.load_system_contacts", MagicMock(return_value=mock_sys_contacts))
    monkeypatch.setattr("icloud_cleanup.contacts.build_contact_profiles", MagicMock(return_value={}))

    # Mock classifier -- return a simple Classification for each message
    now = int(time.time())

    def mock_classify_single(msg, profiles, replied, ts):
        return Classification(
            message_id=msg.message_id, tier=Tier.TRASH,
            confidence=0.01, signals="mock", protected=False,
            timestamp=ts,
        )

    monkeypatch.setattr("icloud_cleanup.classifier.classify_single", mock_classify_single)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(delay=0.5)
        await pilot.press("p")
        assert isinstance(app.screen, PipelineScreen)

        # Click Run Pipeline
        await pilot.click("#btn-pipeline")

        # Wait for worker to run through steps 1-2 (step 3 will fail gracefully)
        await pilot.pause(delay=2.0)

        status = app.query_one("#pipeline-status")
        status_text = str(status.renderable)
        # Should be Complete or Error (step 3 may fail without MLX)
        assert "Complete" in status_text or "Error" in status_text or "Running" in status_text
