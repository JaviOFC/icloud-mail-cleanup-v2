"""Per-screen contextual help overlays shown on first visit."""

from __future__ import annotations

from rich.table import Table

from textual.app import ComposeResult
from textual.widgets import Static

from icloud_cleanup.tui.widgets.dismissible_overlay import DismissibleOverlay

# Screen-specific help: (title, prose_lines, key_action_pairs)
SCREEN_HELP: dict[str, tuple[str, list[str], list[tuple[str, str]]]] = {
    "dashboard": (
        "Dashboard",
        [
            "Overview of your mailbox classification results.",
            "",
            "The [bold]tier summary[/bold] shows how emails are categorized:",
            "  Trash, Active, Historical, and Review.",
            "",
            "The [bold]storage banner[/bold] shows how much space you can reclaim.",
        ],
        [
            ("3", "Go to Review screen"),
            ("1", "Go to Pipeline screen"),
            ("h", "Reopen this help"),
            ("?", "Full keybinding reference"),
        ],
    ),
    "review": (
        "Review",
        [
            "Review and decide on email clusters.",
            "",
            "Use [bold]Auto-Sort[/bold] to auto-resolve high-confidence clusters.",
            "Use [bold]Run API Analysis[/bold] for AI-assisted ambiguous emails.",
            "Check the [bold]Similar Senders[/bold] tab for related sender suggestions.",
        ],
        [
            ("Up/Down", "Navigate cluster list"),
            ("Space", "Select/deselect clusters"),
            ("A", "Approve selected (mark for deletion)"),
            ("S", "Skip selected (keep them)"),
            ("I", "Inspect mode (see individual emails)"),
            ("h", "Reopen this help"),
            ("?", "Full keybinding reference"),
        ],
    ),
    "execute": (
        "Execute",
        [
            "Execute approved email deletions.",
            "",
            "Always start with [bold]Dry Run[/bold] to preview what will happen.",
            "Only use [bold]Execute for Real[/bold] when you're confident.",
        ],
        [
            ("Dry Run", "Preview deletions without acting"),
            ("Execute", "Move approved emails to Trash"),
            ("C", "Cancel a running execution"),
            ("Escape", "Return to Review"),
            ("h", "Reopen this help"),
        ],
    ),
    "pipeline": (
        "Pipeline",
        [
            "Re-run the email analysis pipeline.",
            "",
            "The pipeline has 3 steps:",
            "  1. [bold]Scan[/bold] — read the Mail.app Envelope Index",
            "  2. [bold]Classify[/bold] — categorize emails by metadata signals",
            "  3. [bold]Analyze[/bold] — content analysis via MLX embeddings",
        ],
        [
            ("Run Pipeline", "Start the analysis"),
            ("C", "Cancel the pipeline"),
            ("h", "Reopen this help"),
            ("?", "Full keybinding reference"),
        ],
    ),
}


def _build_keybinding_table(pairs: list[tuple[str, str]]) -> Table:
    """Build a borderless Rich Table for key→action pairs."""
    table = Table(
        show_header=False,
        show_edge=False,
        show_lines=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Key", style="bold cyan", width=12, justify="right")
    table.add_column("Action")
    for key, action in pairs:
        table.add_row(key, action)
    return table


class ScreenHelpOverlay(DismissibleOverlay):
    """Contextual help overlay for a specific screen."""

    def __init__(self, screen_name: str) -> None:
        super().__init__()
        title, prose_lines, key_pairs = SCREEN_HELP.get(
            screen_name, ("Help", ["No help available."], [])
        )
        self.title_text = title
        self._prose_lines = prose_lines
        self._key_pairs = key_pairs

    def compose_body(self) -> ComposeResult:
        if self._prose_lines:
            yield Static(
                "\n".join(self._prose_lines), id="overlay-body", markup=True
            )
        if self._key_pairs:
            yield Static(_build_keybinding_table(self._key_pairs))


def show_screen_help_if_first_visit(screen: "Screen", screen_name: str) -> None:
    """Push a help overlay if this screen hasn't been visited yet this session.

    Only active when the app has ``_show_welcome`` enabled (real user sessions,
    not tests). The dashboard screen is skipped because the welcome overlay
    already provides orientation.
    """
    if not getattr(screen.app, "_show_welcome", False):
        return

    if screen_name == "dashboard":
        return

    visited = getattr(screen.app, "_visited_screens", None)
    if visited is None:
        screen.app._visited_screens = set()
        visited = screen.app._visited_screens

    if screen_name not in visited:
        visited.add(screen_name)
        screen.app.push_screen(ScreenHelpOverlay(screen_name))


def recall_screen_help(screen: "Screen", screen_name: str) -> None:
    """Push a screen help overlay (always, regardless of first-visit state)."""
    screen.app.push_screen(ScreenHelpOverlay(screen_name))
