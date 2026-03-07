"""Textual TUI application for iCloud Mail Cleanup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import work
from textual.app import App
from textual.binding import Binding

from icloud_cleanup.tui.screens import ExecuteScreen, PipelineScreen, ReviewScreen
from icloud_cleanup.tui.screens.dashboard import DashboardScreen
from icloud_cleanup.tui.screens.help_overlay import HelpScreen
from icloud_cleanup.tui.widgets.dismissible_overlay import WelcomeOverlay


class CleanupApp(App):
    """Interactive TUI for reviewing and managing email classifications."""

    CSS_PATH = "app.tcss"

    MODES = {
        "pipeline": PipelineScreen,
        "dashboard": DashboardScreen,
        "review": ReviewScreen,
        "execute": ExecuteScreen,
    }
    DEFAULT_MODE = "dashboard"

    SCREENS = {"help": HelpScreen}

    BINDINGS = [
        Binding("1", "switch_mode('pipeline')", "Pipeline", priority=True),
        Binding("2", "switch_mode('dashboard')", "Dashboard", priority=True),
        Binding("3", "switch_mode('review')", "Review", priority=True),
        Binding("4", "switch_mode('execute')", "Execute", priority=True),
        Binding("question_mark", "push_screen('help')", "Help"),
        Binding("t", "toggle_dark", "Theme"),
        Binding("q", "quit", "Quit"),
    ]

    TITLE = "iCloud Mail Cleanup"

    report_data: dict[str, Any] | None = None
    classifications: dict[int, Any] | None = None
    session: Any | None = None
    messages: list[Any] | None = None
    sender_lookup: dict[int, str] | None = None
    _visited_screens: set[str] | None = None
    _show_welcome: bool = False

    def __init__(
        self,
        checkpoint_path: Path,
        session_path: Path | None = None,
        db_path: Path | None = None,
        *,
        show_welcome: bool = False,
    ) -> None:
        super().__init__()
        self.checkpoint_path = checkpoint_path
        self.session_path = session_path
        self.db_path = db_path
        self._show_welcome = show_welcome
        self._visited_screens = set()

    def on_mount(self) -> None:
        self._load_data()
        if self._show_welcome:
            self.push_screen(WelcomeOverlay())

    @work(thread=True)
    def _load_data(self) -> None:
        """Load checkpoint and build report data in a background thread."""
        from icloud_cleanup.checkpoint import load_checkpoint
        from icloud_cleanup.models import Message
        from icloud_cleanup.report import build_report_data

        checkpoint = load_checkpoint(self.checkpoint_path)
        self.classifications = checkpoint

        if not checkpoint:
            return

        classifications_list = list(checkpoint.values())

        messages: list[Message] = []
        if self.db_path is not None:
            try:
                from icloud_cleanup.scanner import open_db, scan_messages

                conn = open_db(self.db_path)
                try:
                    messages = scan_messages(conn)
                finally:
                    conn.close()
            except Exception:
                messages = []

        if not messages:
            messages = [
                Message(
                    rowid=0,
                    message_id=c.message_id,
                    conversation_id=0,
                    flags=0,
                    read=0,
                    flagged=0,
                    deleted=0,
                    size=0,
                    date_received=c.timestamp,
                    sender_address="",
                    subject="",
                    mailbox_url="",
                    list_id_hash=None,
                    unsubscribe_type=None,
                    automated_conversation=0,
                    model_category=None,
                    model_high_impact=0,
                )
                for c in classifications_list
            ]

        self.messages = messages
        self.sender_lookup = {m.message_id: m.sender_address for m in messages}
        self.report_data = build_report_data(classifications_list, messages)

        if self.session_path:
            try:
                from icloud_cleanup.review import load_session

                self.session = load_session(self.session_path)
            except Exception:
                pass

    def action_toggle_dark(self) -> None:
        """Toggle between dark and light themes."""
        if self.theme == "textual-dark":
            self.theme = "textual-light"
        else:
            self.theme = "textual-dark"
