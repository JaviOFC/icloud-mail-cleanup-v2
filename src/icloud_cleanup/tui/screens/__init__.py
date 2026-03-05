"""TUI screen definitions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from icloud_cleanup.tui.screens.review import ReviewScreen


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


class ExecuteScreen(PlaceholderScreen):
    """Placeholder -- will be replaced in plan 04-03."""

    def __init__(self) -> None:
        super().__init__("Execute -- Coming soon...")


class PipelineScreen(PlaceholderScreen):
    """Placeholder -- will be replaced in plan 04-04."""

    def __init__(self) -> None:
        super().__init__("Pipeline -- Coming soon...")


__all__ = ["ReviewScreen", "ExecuteScreen", "PipelineScreen"]
