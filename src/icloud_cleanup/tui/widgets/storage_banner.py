"""Storage savings banner widget for the Dashboard screen."""

from __future__ import annotations

from textual.widgets import Static


def _format_size(size_bytes: int) -> str:
    """Format byte count to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class StorageBannerWidget(Static):
    """Prominent display of potential storage savings from trash classification."""

    DEFAULT_CSS = """
    StorageBannerWidget {
        height: 3;
        content-align: center middle;
        text-style: bold;
        background: $panel;
        margin: 1 2;
        width: 100%;
    }
    """

    def __init__(
        self,
        total_trash_size: int = 0,
        total_trash_count: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._trash_size = total_trash_size
        self._trash_count = total_trash_count

    def on_mount(self) -> None:
        self._render_stats()

    def update_stats(self, size: int, count: int) -> None:
        """Refresh the banner when review decisions change."""
        self._trash_size = size
        self._trash_count = count
        self._render_stats()

    def _render_stats(self) -> None:
        size_str = _format_size(self._trash_size)
        self.update(
            f"Potential savings: {size_str} ({self._trash_count:,} emails)"
        )
