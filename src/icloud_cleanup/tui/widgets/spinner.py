"""Animated spinner widget for showing active processing."""

from __future__ import annotations

from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Static

SPINNER_FRAMES = ["[bold cyan]\u280b[/]", "[bold cyan]\u2819[/]", "[bold cyan]\u2838[/]", "[bold cyan]\u28b0[/]", "[bold cyan]\u28e0[/]", "[bold cyan]\u28c4[/]", "[bold cyan]\u2846[/]", "[bold cyan]\u2807[/]"]


class SpinnerWidget(Static):
    """A small animated spinner that cycles through braille dot patterns.

    Call ``start()`` to begin animating and ``stop()`` to hide.
    """

    DEFAULT_CSS = """
    SpinnerWidget {
        width: 3;
        height: 1;
        content-align: center middle;
    }
    """

    _frame: reactive[int] = reactive(0)
    _timer: Timer | None = None

    def start(self) -> None:
        """Begin the spinner animation."""
        self.display = True
        if self._timer is None:
            self._timer = self.set_interval(0.1, self._advance)

    def stop(self) -> None:
        """Stop and hide the spinner."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.display = False
        self.update("")

    def _advance(self) -> None:
        self._frame = (self._frame + 1) % len(SPINNER_FRAMES)

    def watch__frame(self, frame: int) -> None:
        self.update(SPINNER_FRAMES[frame])
