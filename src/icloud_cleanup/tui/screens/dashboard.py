"""Dashboard screen showing tier summary and storage savings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Header, Static

from icloud_cleanup.tui.widgets.active_footer import ActiveFooter
from icloud_cleanup.tui.widgets.screen_help import show_screen_help_if_first_visit
from icloud_cleanup.tui.widgets.storage_banner import StorageBannerWidget
from icloud_cleanup.tui.widgets.tier_summary import TierSummaryWidget


class DashboardScreen(Screen):
    """Main dashboard showing tier summary and storage savings."""

    CSS_PATH = "dashboard.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="dashboard-content"):
            yield StorageBannerWidget(id="storage-banner")
            yield TierSummaryWidget(id="tier-summary")
            yield Static("Pipeline: Ready", id="pipeline-status")
        yield ActiveFooter()

    def on_mount(self) -> None:
        self._check_data()
        show_screen_help_if_first_visit(self, "dashboard")

    def _check_data(self) -> None:
        """Populate widgets with report data if available."""
        report_data = self.app.report_data
        if report_data is None:
            # Data still loading -- set a timer to recheck
            self.set_timer(0.3, self._check_data)
            return

        tiers = report_data.get("tiers", {})
        trash = tiers.get("trash", {})
        trash_size = trash.get("size", 0)
        trash_count = trash.get("count", 0)

        banner = self.query_one("#storage-banner", StorageBannerWidget)
        banner.update_stats(trash_size, trash_count)

        summary = self.query_one("#tier-summary", TierSummaryWidget)
        summary.update_data(report_data)

        status = self.query_one("#pipeline-status", Static)
        status.update("Pipeline: Data loaded from checkpoint")
