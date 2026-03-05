"""Dashboard screen -- placeholder, will be fully built in Task 2."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class DashboardScreen(Screen):
    """Main dashboard showing tier summary and storage savings."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Dashboard -- Loading...", id="dashboard-placeholder")
        yield Footer()
