"""Custom footer that highlights the active screen/mode."""

from __future__ import annotations

from rich.text import Text
from textual.app import RenderResult
from textual.widgets import Static

# Mode keys and their labels
MODE_KEYS = [
    ("1", "Pipeline", "pipeline"),
    ("2", "Dashboard", "dashboard"),
    ("3", "Review", "review"),
    ("4", "Execute", "execute"),
]

EXTRA_KEYS = [
    ("?", "Help"),
    ("t", "Theme"),
    ("q", "Quit"),
]


class ActiveFooter(Static):
    """Footer bar that highlights the currently active screen mode.

    Reads ``app.current_mode`` on each render to determine the active tab.
    """

    DEFAULT_CSS = """
    ActiveFooter {
        dock: bottom;
        height: 1;
        width: 100%;
        background: $panel;
    }
    """

    def on_mount(self) -> None:
        # Re-render periodically to catch mode changes
        self.set_interval(0.3, self.refresh)

    def render(self) -> RenderResult:
        current = getattr(self.app, "current_mode", "dashboard")
        parts = Text()

        for key, label, mode_name in MODE_KEYS:
            is_active = mode_name == current

            if is_active:
                parts.append(f" {key.upper()} ", style="bold reverse")
                parts.append(f" {label} ", style="bold")
            else:
                parts.append(f" {key.upper()} ", style="bold dim")
                parts.append(f"{label} ", style="dim")
            parts.append(" ")

        parts.append("  ")

        for key, label in EXTRA_KEYS:
            parts.append(f" {key} ", style="bold dim")
            parts.append(f"{label} ", style="dim")

        return parts
