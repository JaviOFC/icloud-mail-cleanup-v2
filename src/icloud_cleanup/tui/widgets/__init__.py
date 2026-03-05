"""TUI widgets for iCloud Mail Cleanup."""

from icloud_cleanup.tui.widgets.cluster_detail import ClusterDetailWidget
from icloud_cleanup.tui.widgets.cluster_list import ClusterListWidget
from icloud_cleanup.tui.widgets.confidence_bar import ConfidenceBar
from icloud_cleanup.tui.widgets.propagation_tab import PropagationTabWidget

__all__ = [
    "ClusterDetailWidget",
    "ClusterListWidget",
    "ConfidenceBar",
    "PropagationTabWidget",
]
