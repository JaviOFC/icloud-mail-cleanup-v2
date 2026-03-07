"""TUI screen definitions."""

from __future__ import annotations

from icloud_cleanup.tui.screens.review import ReviewScreen
from icloud_cleanup.tui.screens.execute import ExecuteScreen as ExecuteScreen  # noqa: E501
from icloud_cleanup.tui.screens.pipeline import PipelineScreen as PipelineScreen  # noqa: E501

__all__ = ["ReviewScreen", "ExecuteScreen", "PipelineScreen"]
