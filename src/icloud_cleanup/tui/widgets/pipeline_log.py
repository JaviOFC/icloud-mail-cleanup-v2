"""Pipeline log widget: styled RichLog for build-output style display."""

from __future__ import annotations

from textual.widgets import RichLog


class PipelineLogWidget(RichLog):
    """Scrollable log with convenience methods for pipeline step output."""

    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, auto_scroll=True, max_lines=1000, **kwargs)

    def log_step(self, step_name: str) -> None:
        """Write a bold step header."""
        self.write(f"\n[bold]{step_name}[/bold]")

    def log_info(self, msg: str) -> None:
        """Write a normal informational line."""
        self.write(f"  {msg}")

    def log_error(self, msg: str) -> None:
        """Write a red error line."""
        self.write(f"  [red]{msg}[/red]")

    def log_success(self, msg: str) -> None:
        """Write a green success line."""
        self.write(f"  [green]{msg}[/green]")
