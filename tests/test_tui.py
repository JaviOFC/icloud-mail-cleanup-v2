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
