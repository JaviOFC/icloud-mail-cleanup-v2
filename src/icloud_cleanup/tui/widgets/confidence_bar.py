"""Confidence bar widget rendering a colored horizontal bar."""

from __future__ import annotations

from rich.text import Text

from textual.widgets import Static


_BAR_WIDTH = 20


class ConfidenceBar(Static):
    """Renders a colored bar proportional to a confidence value (0.0-1.0)."""

    DEFAULT_CSS = """
    ConfidenceBar {
        height: 1;
        width: auto;
    }
    """

    def __init__(self, confidence: float = 0.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._confidence = max(0.0, min(1.0, confidence))

    def on_mount(self) -> None:
        self._render_bar()

    def update_confidence(self, confidence: float) -> None:
        self._confidence = max(0.0, min(1.0, confidence))
        self._render_bar()

    def _render_bar(self) -> None:
        filled = round(self._confidence * _BAR_WIDTH)
        empty = _BAR_WIDTH - filled

        if self._confidence < 0.3:
            color = "red"
        elif self._confidence < 0.7:
            color = "yellow"
        else:
            color = "green"

        bar = Text()
        bar.append("\u2588" * filled, style=color)
        bar.append("\u2591" * empty, style="dim")
        bar.append(f" {self._confidence:.2f}")
        self.update(bar)
