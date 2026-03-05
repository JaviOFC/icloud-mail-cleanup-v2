"""TUI screen definitions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Static

from icloud_cleanup.tui.widgets.active_footer import ActiveFooter

from icloud_cleanup.tui.screens.review import ReviewScreen
from icloud_cleanup.tui.screens.execute import ExecuteScreen as ExecuteScreen  # noqa: E501
from icloud_cleanup.tui.screens.pipeline import PipelineScreen as PipelineScreen  # noqa: E501


class PlaceholderScreen(Screen):
    """Base placeholder screen showing a 'Coming soon...' message."""

    DEFAULT_CSS = """
    PlaceholderScreen {
        align: center middle;
    }
    .placeholder-label {
        text-align: center;
        width: auto;
    }
    """

    def __init__(self, label: str = "Coming soon...") -> None:
        super().__init__()
        self._label = label

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._label, classes="placeholder-label")
        yield ActiveFooter()


__all__ = ["ReviewScreen", "ExecuteScreen", "PipelineScreen", "HelpScreen"]
