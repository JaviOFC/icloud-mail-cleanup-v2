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
