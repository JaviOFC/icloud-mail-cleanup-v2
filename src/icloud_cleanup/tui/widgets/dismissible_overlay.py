"""Reusable dismissible overlay that closes on any keypress."""

from __future__ import annotations

from rich.table import Table

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static


class DismissibleOverlay(ModalScreen[None]):
    """A centered modal overlay that dismisses on any keypress.

    Subclass and override ``body_text`` or ``compose_body()`` for custom content.
    """

    DEFAULT_CSS = """
    DismissibleOverlay {
        align: center middle;
    }

    DismissibleOverlay > #overlay-container {
        width: 60%;
        min-width: 60;
        max-width: 100;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    DismissibleOverlay > #overlay-container > #overlay-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }

    DismissibleOverlay > #overlay-container > #overlay-body {
        text-align: left;
        width: 100%;
    }

    DismissibleOverlay > #overlay-container > #overlay-hint {
        text-align: center;
        width: 100%;
        margin-top: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
    ]

    title_text: str = ""
    body_text: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="overlay-container"):
            if self.title_text:
                yield Static(self.title_text, id="overlay-title")
            yield from self.compose_body()
            yield Static("Press any key to continue", id="overlay-hint")

    def compose_body(self) -> ComposeResult:
        """Override to provide custom body content."""
        if self.body_text:
            yield Static(self.body_text, id="overlay-body")

    def on_key(self, event: Key) -> None:
        """Dismiss on any keypress."""
        event.prevent_default()
        self.dismiss(None)


def _build_nav_table() -> Table:
    """Build a borderless Rich Table for the welcome overlay navigation keys."""
    table = Table(
        show_header=False,
        show_edge=False,
        show_lines=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Key", style="bold cyan", width=6, justify="right")
    table.add_column("Screen")
    table.add_column("Description")
    table.add_row("1", "Pipeline", "re-scan and reclassify emails")
    table.add_row("2", "Dashboard", "tier summary and storage savings")
    table.add_row("3", "Review", "inspect and approve email clusters")
    table.add_row("4", "Execute", "run approved deletions (dry-run first)")
    return table


class WelcomeOverlay(DismissibleOverlay):
    """Welcome overlay shown on first launch."""

    title_text = "iCloud Mail Cleanup"

    def compose_body(self) -> ComposeResult:
        yield Static(
            "Analyze, review, and clean up your iCloud mailbox.\n"
            "\n"
            "Navigate screens with keyboard shortcuts:",
            id="overlay-body",
            markup=True,
        )
        yield Static(_build_nav_table())
        yield Static(
            "Press [bold]?[/bold] anytime for the full keybinding reference.\n"
            "Press [bold]h[/bold] for screen-specific help.\n"
            "Press [bold]T[/bold] to toggle dark/light theme.",
            markup=True,
        )
