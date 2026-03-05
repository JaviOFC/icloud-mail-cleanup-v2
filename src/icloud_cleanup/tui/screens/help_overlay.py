"""Help overlay showing keyboard shortcut reference."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


def _build_section(title: str, rows: list[tuple[str, str]]) -> Table:
    """Build a Rich table for a keybinding section."""
    table = Table(
        title=title,
        show_header=True,
        header_style="bold",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Key", style="bold cyan", width=12)
    table.add_column("Action")
    for key, action in rows:
        table.add_row(key, action)
    return table


class HelpScreen(ModalScreen):
    """Modal overlay displaying keyboard shortcuts by section."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("question_mark", "dismiss", "Close", priority=True),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen > #help-container {
        width: 60;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    HelpScreen > #help-container > #help-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Static("Keyboard Shortcuts", id="help-title")

            global_table = _build_section("Global", [
                ("D", "Dashboard"),
                ("R", "Review"),
                ("E", "Execute"),
                ("P", "Pipeline"),
                ("T", "Toggle theme"),
                ("?", "This help"),
                ("Q", "Quit"),
            ])
            yield Static(global_table)

            review_table = _build_section("Review Screen", [
                ("Up/Down", "Navigate clusters"),
                ("Space", "Toggle selection"),
                ("A", "Approve selected"),
                ("S", "Skip selected"),
                ("I", "Toggle inspect (show emails)"),
            ])
            yield Static(review_table)

            execute_table = _build_section("Execute Screen", [
                ("Enter", "Start execution"),
                ("C", "Cancel execution"),
            ])
            yield Static(execute_table)

            pipeline_table = _build_section("Pipeline Screen", [
                ("Enter", "Start pipeline"),
                ("C", "Cancel pipeline"),
            ])
            yield Static(pipeline_table)
