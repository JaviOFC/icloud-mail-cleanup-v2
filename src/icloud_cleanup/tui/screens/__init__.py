"""TUI screen definitions -- placeholders for screens not yet implemented."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


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
        yield Footer()


class ReviewScreen(PlaceholderScreen):
    """Placeholder -- will be replaced in plan 04-02."""

    def __init__(self) -> None:
        super().__init__("Review -- Coming soon...")


from icloud_cleanup.tui.screens.execute import ExecuteScreen as ExecuteScreen  # noqa: E501


class PipelineScreen(PlaceholderScreen):
    """Placeholder -- will be replaced in plan 04-04."""

    def __init__(self) -> None:
        super().__init__("Pipeline -- Coming soon...")


# Re-export for convenience. DashboardScreen added after task 2.
__all__ = ["ReviewScreen", "ExecuteScreen", "PipelineScreen"]
