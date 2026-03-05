"""Execute screen: live deletion progress with dry-run default."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ProgressBar, RichLog, Static
from textual.worker import get_current_worker

from icloud_cleanup.tui.widgets.screen_help import show_screen_help_if_first_visit
from icloud_cleanup.tui.widgets.spinner import SpinnerWidget


class ExecuteScreen(Screen):
    """Execute approved deletions with progress feedback.

    Dry-run is the default. User must click 'Execute for Real' to actually
    move messages to Trash via AppleScript.
    """

    CSS_PATH = "execute.tcss"

    BINDINGS = [
        ("c", "cancel_execution", "Cancel"),
        ("escape", "switch_mode('review')", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="execute-content"):
            yield Static("Loading session data...", id="exec-summary")
            with Horizontal(id="exec-buttons"):
                yield Button("Dry Run", id="btn-dry", variant="primary")
                yield Button("Execute for Real", id="btn-execute", variant="error")
            with Horizontal(id="exec-progress-row"):
                yield ProgressBar(id="exec-progress", total=100, show_eta=False)
                yield SpinnerWidget(id="exec-spinner")
            yield Static("Success: 0 | Errors: 0 | Skipped: 0", id="exec-stats")
            yield RichLog(id="exec-log", markup=True, auto_scroll=True, max_lines=500)
        yield Footer()

    def on_mount(self) -> None:
        self._update_summary()
        show_screen_help_if_first_visit(self, "execute")

    def _update_summary(self) -> None:
        """Compute and display summary of approved items from session."""
        session = self.app.session
        classifications = self.app.classifications
        summary_widget = self.query_one("#exec-summary", Static)

        if session is None or classifications is None:
            summary_widget.update("No review session loaded. Complete a review first.")
            return

        approved_ids = self._collect_approved_ids()
        if not approved_ids:
            summary_widget.update("No items approved for deletion.")
            return

        approved_count = len(approved_ids)
        total_size = 0
        if self.app.report_data:
            # Estimate from classifications
            for mid in approved_ids:
                cls = classifications.get(mid)
                if cls is not None:
                    total_size += 1  # placeholder for size

        cluster_count = sum(
            1 for d in session.decisions.values()
            if d.get("action") == "approve"
        )

        summary_widget.update(
            f"Approved: {approved_count} emails from {cluster_count} clusters"
        )

    def _collect_approved_ids(self) -> set[int]:
        """Collect all approved message IDs from session decisions."""
        session = self.app.session
        classifications = self.app.classifications
        if session is None or classifications is None:
            return set()

        approved_ids: set[int] = set()

        # Cluster-level approvals
        all_cls = list(classifications.values())
        for cluster_key, decision in session.decisions.items():
            if decision.get("action") == "approve":
                for c in all_cls:
                    key = _cluster_key(c)
                    if key == cluster_key:
                        approved_ids.add(c.message_id)

        # Individual approvals
        for mid_str, decision in session.individual_decisions.items():
            if decision.get("action") == "approve":
                approved_ids.add(int(mid_str))

        return approved_ids

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-dry":
            self._run(dry_run=True)
        elif event.button.id == "btn-execute":
            self.notify(
                "Executing for real -- this moves emails to Trash!",
                severity="warning",
            )
            self._run(dry_run=False)

    @work(exclusive=True, thread=True)
    def _run(self, dry_run: bool) -> None:
        """Execute deletions in a background thread with progress updates."""
        from icloud_cleanup.executor import ActionLog, execute_deletions
        from icloud_cleanup.models import Message
        from icloud_cleanup.scanner import open_db, scan_messages

        worker = get_current_worker()
        log_widget = self.query_one("#exec-log", RichLog)
        progress = self.query_one("#exec-progress", ProgressBar)
        stats_widget = self.query_one("#exec-stats", Static)

        spinner = self.query_one("#exec-spinner", SpinnerWidget)
        self.app.call_from_thread(spinner.start)

        mode = "DRY-RUN" if dry_run else "LIVE"
        self.app.call_from_thread(log_widget.write, f"[bold]Starting execution ({mode})...[/bold]")

        # Disable buttons during execution
        self.app.call_from_thread(self.query_one("#btn-dry", Button).set_class, True, "hidden")
        self.app.call_from_thread(self.query_one("#btn-execute", Button).set_class, True, "hidden")

        approved_ids = self._collect_approved_ids()
        if not approved_ids:
            self.app.call_from_thread(log_widget.write, "[yellow]No approved items to execute.[/yellow]")
            return

        classifications = self.app.classifications
        if classifications is None:
            self.app.call_from_thread(log_widget.write, "[red]No classifications loaded.[/red]")
            return

        # Load messages from DB
        messages: list[Message] = []
        try:
            db_path = self.app.db_path
            conn = open_db(db_path)
            try:
                messages = scan_messages(conn)
            finally:
                conn.close()
        except Exception as e:
            self.app.call_from_thread(
                log_widget.write,
                f"[red]Could not load messages from database: {e}[/red]",
            )
            return

        approved_messages = [m for m in messages if m.message_id in approved_ids]
        approved_classifications = {
            mid: classifications[mid]
            for mid in approved_ids
            if mid in classifications
        }

        total = len(approved_messages)
        self.app.call_from_thread(progress.update, total=total, progress=0)
        self.app.call_from_thread(
            log_widget.write,
            f"Processing {total} approved messages...",
        )

        if worker.is_cancelled:
            self.app.call_from_thread(log_widget.write, "[yellow]Cancelled.[/yellow]")
            return

        # Execute in chunks for progress granularity
        batch_size = 100
        cumulative_success = 0
        cumulative_errors = 0
        cumulative_skipped = 0
        action_log = ActionLog(self._action_log_path())

        try:
            for batch_start in range(0, total, batch_size):
                if worker.is_cancelled:
                    self.app.call_from_thread(
                        log_widget.write, "[yellow]Execution cancelled by user.[/yellow]"
                    )
                    break

                batch_msgs = approved_messages[batch_start : batch_start + batch_size]
                result = execute_deletions(
                    batch_msgs,
                    approved_classifications,
                    action_log,
                    dry_run=dry_run,
                    batch_size=batch_size,
                    batch_pause=0.0 if dry_run else 2.0,
                )

                cumulative_success += result["success_count"]
                cumulative_errors += result["error_count"]
                cumulative_skipped += result["skipped_protected"]

                self.app.call_from_thread(
                    progress.update, progress=batch_start + len(batch_msgs)
                )
                self.app.call_from_thread(
                    stats_widget.update,
                    f"Success: {cumulative_success} | Errors: {cumulative_errors} | Skipped: {cumulative_skipped}",
                )
                self.app.call_from_thread(
                    log_widget.write,
                    f"Batch {batch_start // batch_size + 1}: "
                    f"+{result['success_count']} ok, "
                    f"+{result['error_count']} errors, "
                    f"+{result['skipped_protected']} skipped",
                )

                if result["errors"]:
                    for err in result["errors"][:3]:
                        self.app.call_from_thread(log_widget.write, f"  [red]{err}[/red]")
        finally:
            action_log.close()

        # Final summary
        self.app.call_from_thread(
            log_widget.write,
            f"\n[bold]Execution complete ({mode}):[/bold] "
            f"{cumulative_success} success, {cumulative_errors} errors, "
            f"{cumulative_skipped} skipped",
        )
        self.app.call_from_thread(
            self.notify,
            f"Execution complete: {cumulative_success} messages processed",
        )

        # Stop spinner and re-show buttons
        self.app.call_from_thread(spinner.stop)
        self.app.call_from_thread(self.query_one("#btn-dry", Button).set_class, False, "hidden")
        self.app.call_from_thread(self.query_one("#btn-execute", Button).set_class, False, "hidden")

    def _action_log_path(self) -> "Path":
        from pathlib import Path

        return Path.home() / ".icloud-cleanup" / "action_log.db"

    def action_cancel_execution(self) -> None:
        """Cancel the running execution worker."""
        self.workers.cancel_all()
        self.notify("Cancelling execution...", severity="warning")


def _cluster_key(c: "Classification") -> str:
    """Normalize cluster label for grouping (mirrors review.py logic)."""
    if c.cluster_id is None or c.cluster_id == -1:
        return "Unclustered"
    return c.cluster_label or f"cluster_{c.cluster_id}"
