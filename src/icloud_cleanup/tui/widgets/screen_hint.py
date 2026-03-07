"""Persistent single-line hint bar showing available keys per screen."""

from __future__ import annotations

from textual.widgets import Static

# Hint text per screen name
SCREEN_HINTS: dict[str, str] = {
    "pipeline": "1 Pipeline  2 Dashboard  3 Review  4 Execute  |  h Screen Help  ? Keys  T Theme",
    "dashboard": "1 Pipeline  2 Dashboard  3 Review  4 Execute  |  h Screen Help  ? Keys  T Theme",
    "review": "Space Select  A Approve  S Skip  I Inspect  |  h Screen Help  ? Keys",
    "execute": "Dry Run  Execute  |  C Cancel  Esc Back  |  h Screen Help  ? Keys",
}


class ScreenHintBar(Static):
    """A persistent 1-line bar showing available keybindings for the current screen."""

    DEFAULT_CSS = """
    ScreenHintBar {
        dock: top;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 2;
    }
    """

    def __init__(self, screen_name: str, **kwargs) -> None:
        hint = SCREEN_HINTS.get(screen_name, "")
        super().__init__(hint, **kwargs)
