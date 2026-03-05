"""Reusable dismissible overlay that closes on any keypress."""

from __future__ import annotations

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
        width: 64;
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
        text-align: center;
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


class WelcomeOverlay(DismissibleOverlay):
    """Welcome overlay shown on first launch."""

    title_text = "iCloud Mail Cleanup"
    body_text = (
        "Analyze, review, and clean up your iCloud mailbox.\n"
        "\n"
        "Navigate screens with keyboard shortcuts:\n"
        "  [bold]D[/bold] Dashboard  -  tier summary and storage savings\n"
        "  [bold]R[/bold] Review     -  inspect and approve email clusters\n"
        "  [bold]E[/bold] Execute    -  run approved deletions (dry-run first)\n"
        "  [bold]P[/bold] Pipeline   -  re-scan and reclassify emails\n"
        "\n"
        "Press [bold]?[/bold] anytime for the full keybinding reference.\n"
        "Press [bold]T[/bold] to toggle dark/light theme."
    )

    DEFAULT_CSS = """
    WelcomeOverlay {
        align: center middle;
    }

    WelcomeOverlay > #overlay-container {
        width: 64;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    WelcomeOverlay > #overlay-container > #overlay-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }

    WelcomeOverlay > #overlay-container > #overlay-body {
        width: 100%;
    }

    WelcomeOverlay > #overlay-container > #overlay-hint {
        text-align: center;
        width: 100%;
        margin-top: 1;
        color: $text-muted;
    }
    """

    def compose_body(self) -> ComposeResult:
        yield Static(self.body_text, id="overlay-body", markup=True)
