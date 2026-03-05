"""Per-screen contextual help overlays shown on first visit."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from icloud_cleanup.tui.widgets.dismissible_overlay import DismissibleOverlay

# Screen-specific help text (screen_name -> (title, body))
SCREEN_HELP: dict[str, tuple[str, str]] = {
    "dashboard": (
        "Dashboard",
        "Overview of your mailbox classification results.\n"
        "\n"
        "The [bold]tier summary[/bold] shows how emails are categorized:\n"
        "  Trash    - safe to delete (junk, spam, old newsletters)\n"
        "  Active   - recent personal/important emails (protected)\n"
        "  Historical - old but possibly meaningful emails\n"
        "  Review   - ambiguous emails needing your decision\n"
        "\n"
        "The [bold]storage banner[/bold] shows how much space you can reclaim.\n"
        "\n"
        "Press [bold]R[/bold] to start reviewing email clusters.",
    ),
    "review": (
        "Review",
        "Review and decide on email clusters.\n"
        "\n"
        "  [bold]Up/Down[/bold]  Navigate cluster list\n"
        "  [bold]Space[/bold]    Select/deselect clusters\n"
        "  [bold]A[/bold]        Approve selected (mark for deletion)\n"
        "  [bold]S[/bold]        Skip selected (keep them)\n"
        "  [bold]I[/bold]        Inspect mode (see individual emails)\n"
        "\n"
        "Use [bold]Auto-Triage[/bold] to auto-resolve high-confidence clusters.\n"
        "Use [bold]Run API Analysis[/bold] for AI-assisted ambiguous emails.\n"
        "Check the [bold]Propagation[/bold] tab for similar-sender suggestions.",
    ),
    "execute": (
        "Execute",
        "Execute approved email deletions.\n"
        "\n"
        "Always start with [bold]Dry Run[/bold] to preview what will happen.\n"
        "Only use [bold]Execute for Real[/bold] when you're confident.\n"
        "\n"
        "The progress bar and log show real-time execution status.\n"
        "Press [bold]C[/bold] to cancel a running execution.\n"
        "Press [bold]Escape[/bold] to return to Review.",
    ),
    "pipeline": (
        "Pipeline",
        "Re-run the email analysis pipeline.\n"
        "\n"
        "The pipeline has 3 steps:\n"
        "  1. [bold]Scan[/bold]     - read the Mail.app Envelope Index\n"
        "  2. [bold]Classify[/bold] - categorize emails by metadata signals\n"
        "  3. [bold]Analyze[/bold]  - content analysis via MLX embeddings\n"
        "\n"
        "Click [bold]Run Pipeline[/bold] to start. Progress is shown live.\n"
        "Press [bold]C[/bold] to cancel. Results update the Dashboard & Review.",
    ),
}


class ScreenHelpOverlay(DismissibleOverlay):
    """Contextual help overlay for a specific screen."""

    def __init__(self, screen_name: str) -> None:
        super().__init__()
        title, body = SCREEN_HELP.get(screen_name, ("Help", "No help available."))
        self.title_text = title
        self._body_markup = body

    def compose_body(self) -> ComposeResult:
        yield Static(self._body_markup, id="overlay-body", markup=True)


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
