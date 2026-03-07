"""Review screen with cluster list, detail panel, propagation tab, and API fallback."""

from __future__ import annotations

import time
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Header,
    Static,
    TabbedContent,
    TabPane,
)

from icloud_cleanup.api_fallback import (
    build_metadata_payload,
    classify_ambiguous_batch,
    estimate_api_cost,
)
from icloud_cleanup.auto_triage import auto_triage
from icloud_cleanup.models import Classification, Message, Tier
from icloud_cleanup.propagation import find_propagation_targets
from icloud_cleanup.review import (
    ReviewSession,
    get_session_path,
    load_session,
    save_session,
)
from icloud_cleanup.tui.widgets.active_footer import ActiveFooter
from icloud_cleanup.tui.widgets.cluster_detail import ClusterDetailWidget
from icloud_cleanup.tui.widgets.cluster_list import ClusterListWidget
from icloud_cleanup.tui.widgets.propagation_tab import PropagationTabWidget
from icloud_cleanup.tui.widgets.screen_help import recall_screen_help, show_screen_help_if_first_visit
from icloud_cleanup.tui.widgets.screen_hint import ScreenHintBar


class ReviewScreen(Screen):
    """Primary review surface for classification results."""

    CSS_PATH = "review.tcss"

    BINDINGS = [
        Binding("space", "toggle_select", "Select", show=True),
        Binding("a", "approve_selected", "Approve", show=True),
        Binding("s", "skip_selected", "Skip", show=True),
        Binding("i", "toggle_inspect", "Inspect", show=True),
        Binding("h", "screen_help", "Screen Help", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._all_clusters: list[dict] = []
        self._cluster_index: dict[str, dict] = {}
        self._cluster_classifications: dict[str, list[Classification]] = {}
        self._inspect_active = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScreenHintBar("review")
        with TabbedContent(id="review-tabs"):
            with TabPane("Clusters", id="tab-clusters"):
                with Horizontal(id="review-split"):
                    with Vertical(id="left-panel"):
                        yield Static("Clusters", id="cluster-header", classes="section-header")
                        yield ClusterListWidget(id="cluster-table")
                        with Horizontal(id="bulk-actions"):
                            yield Button("Auto-Sort", id="btn-triage", variant="primary")
                            yield Button("Approve", id="btn-approve", variant="error")
                            yield Button("Skip", id="btn-skip", variant="success")
                            yield Button("API Analyze", id="btn-api", variant="warning")
                    with Vertical(id="right-panel"):
                        yield ClusterDetailWidget(id="cluster-detail")
                yield Static("Loading...", id="api-status")
            with TabPane("Similar Senders", id="tab-propagation"):
                yield PropagationTabWidget(id="propagation-tab")
        yield ActiveFooter()

    def on_mount(self) -> None:
        self._check_data()
        show_screen_help_if_first_visit(self, "review")

    def _check_data(self) -> None:
        """Wait for app data to load, then populate."""
        if self.app.report_data is None:
            self.set_timer(0.3, self._check_data)
            return
        self._populate()

    def _populate(self) -> None:
        """Build cluster list from report data and load session state."""
        report_data = self.app.report_data
        if not report_data:
            return

        classifications = self.app.classifications or {}
        session = self.app.session

        # Build flat cluster list across all tiers
        self._all_clusters = []
        self._cluster_index.clear()
        tiers = report_data.get("tiers", {})
        seen_labels: set[str] = set()
        for tier_value, tier_data in tiers.items():
            for cluster in tier_data.get("clusters", []):
                enriched = dict(cluster)
                enriched["tier"] = tier_value
                # Disambiguate duplicate labels across tiers
                label = cluster["label"]
                if label in seen_labels:
                    label = f"{label} ({tier_value})"
                    enriched["label"] = label
                seen_labels.add(label)
                self._all_clusters.append(enriched)
                self._cluster_index[label] = enriched

        # Build per-cluster classifications
        self._cluster_classifications.clear()
        for c in classifications.values():
            label = c.cluster_label or "Unclustered"
            if c.cluster_id is None or c.cluster_id == -1:
                label = "Unclustered"
            self._cluster_classifications.setdefault(label, []).append(c)

        # Determine already-decided clusters from session
        decided: set[str] = set()
        if session:
            decided = set(session.decisions.keys())

        # Load cluster list
        cluster_table = self.query_one("#cluster-table", ClusterListWidget)
        cluster_table.load_clusters(self._all_clusters, decided=decided)

        # Update API status
        self._update_api_status()

    def _get_sender_lookup(self) -> dict[int, str]:
        """Build message_id -> sender_address mapping."""
        messages = getattr(self.app, "messages", None) or []
        if not messages:
            # Fallback: build from classifications with empty senders
            return {}
        return {m.message_id: m.sender_address for m in messages}

    def _get_messages(self) -> list[Message]:
        return getattr(self.app, "messages", None) or []

    def _get_remaining_review_count(self) -> int:
        """Count Review-tier classifications not yet decided."""
        classifications = self.app.classifications or {}
        session = self.app.session
        decided_ids: set[int] = set()
        if session:
            for label, dec in session.decisions.items():
                for c in classifications.values():
                    cl_label = c.cluster_label or "Unclustered"
                    if c.cluster_id is None or c.cluster_id == -1:
                        cl_label = "Unclustered"
                    if cl_label == label:
                        decided_ids.add(c.message_id)
            for mid_str in session.individual_decisions:
                try:
                    decided_ids.add(int(mid_str))
                except ValueError:
                    pass

        count = 0
        for c in classifications.values():
            if c.tier == Tier.REVIEW and c.message_id not in decided_ids:
                count += 1
        return count

    def _update_api_status(self) -> None:
        """Update the API status bar with remaining count and cost."""
        remaining = self._get_remaining_review_count()
        status = self.query_one("#api-status", Static)
        if remaining == 0:
            status.update("All Review-tier emails have been decided.")
            return

        cost = estimate_api_cost(remaining)
        status.update(
            f"{remaining} Review-tier emails remaining. "
            f"Estimated API cost: ${cost['estimated_cost_usd']:.4f}"
        )

    def _ensure_session(self) -> Any:
        """Ensure a ReviewSession exists on the app."""
        if self.app.session is None:
            self.app.session = ReviewSession(
                session_id=f"tui-{int(time.time())}",
                started_at=int(time.time()),
                last_updated=int(time.time()),
            )
        return self.app.session

    def _save_session(self) -> None:
        """Save current session to disk."""
        session = self.app.session
        if session is None:
            return
        session_path = getattr(self.app, "session_path", None)
        if session_path is None:
            session_path = get_session_path()
        save_session(session, session_path)

    # --- Event handlers ---

    def on_cluster_list_widget_changed(self, event: ClusterListWidget.Changed) -> None:
        """Update detail panel when a cluster row is highlighted."""
        label = event.cluster_label
        cluster_data = self._cluster_index.get(label)
        if not cluster_data:
            return

        detail = self.query_one("#cluster-detail", ClusterDetailWidget)
        cluster_cls = self._cluster_classifications.get(label, [])
        messages = self._get_messages()
        detail.show_cluster(cluster_data, cluster_cls, messages)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-approve":
            self.action_approve_selected()
        elif button_id == "btn-skip":
            self.action_skip_selected()
        elif button_id == "btn-triage":
            self._run_auto_triage()
        elif button_id == "btn-api":
            self._run_api_analysis()

    def on_propagation_tab_widget_applied(
        self, event: PropagationTabWidget.Applied
    ) -> None:
        """Handle bulk-approve of propagation suggestions."""
        prop_tab = self.query_one("#propagation-tab", PropagationTabWidget)
        session = self._ensure_session()
        ts = int(time.time())

        for idx in event.suggestion_indices:
            if idx >= len(prop_tab.suggestions):
                continue
            suggestion = prop_tab.suggestions[idx]
            for mid in suggestion.target_message_ids:
                session.individual_decisions[str(mid)] = {
                    "action": suggestion.suggested_action,
                    "timestamp": ts,
                }
            session.propagation_applied.append({
                "source": suggestion.source_sender,
                "targets": suggestion.target_senders,
                "action": suggestion.suggested_action,
                "message_ids": suggestion.target_message_ids,
            })

        self._save_session()
        self._update_api_status()
        self.notify(
            f"Applied {len(event.suggestion_indices)} propagation suggestions.",
            title="Propagation",
            severity="information",
        )

    # --- Actions ---

    def action_toggle_select(self) -> None:
        cluster_table = self.query_one("#cluster-table", ClusterListWidget)
        cluster_table.key_space()

    def action_approve_selected(self) -> None:
        cluster_table = self.query_one("#cluster-table", ClusterListWidget)
        selected = cluster_table.get_selected()
        if not selected:
            self.notify("No clusters selected. Use Space to select.", severity="warning")
            return

        session = self._ensure_session()
        classifications = self.app.classifications or {}
        ts = int(time.time())
        newly_decided: set[str] = set()

        all_decided_ids: set[int] = set()
        for mid_str in session.individual_decisions:
            try:
                all_decided_ids.add(int(mid_str))
            except ValueError:
                pass
        for label, dec in session.decisions.items():
            for c in classifications.values():
                cl = c.cluster_label or "Unclustered"
                if c.cluster_id is None or c.cluster_id == -1:
                    cl = "Unclustered"
                if cl == label:
                    all_decided_ids.add(c.message_id)

        for label in selected:
            cluster_cls = self._cluster_classifications.get(label, [])
            message_ids = [c.message_id for c in cluster_cls]
            session.decisions[label] = {
                "action": "approve",
                "message_ids": message_ids,
                "timestamp": ts,
            }
            newly_decided.add(label)
            all_decided_ids.update(message_ids)

        self._save_session()

        # Mark decided in UI
        cluster_table.mark_decided(newly_decided)

        # Check propagation for approved clusters
        self._check_propagation(selected, "approve", all_decided_ids)

        self._update_api_status()
        self.notify(
            f"Approved {len(selected)} cluster(s).",
            title="Approved",
            severity="information",
        )

    def action_skip_selected(self) -> None:
        cluster_table = self.query_one("#cluster-table", ClusterListWidget)
        selected = cluster_table.get_selected()
        if not selected:
            self.notify("No clusters selected. Use Space to select.", severity="warning")
            return

        session = self._ensure_session()
        ts = int(time.time())
        newly_decided: set[str] = set()

        for label in selected:
            cluster_cls = self._cluster_classifications.get(label, [])
            message_ids = [c.message_id for c in cluster_cls]
            session.decisions[label] = {
                "action": "skip",
                "message_ids": message_ids,
                "timestamp": ts,
            }
            newly_decided.add(label)

        self._save_session()
        cluster_table.mark_decided(newly_decided)
        self._update_api_status()
        self.notify(
            f"Skipped {len(selected)} cluster(s).",
            title="Skipped",
            severity="information",
        )

    def action_toggle_inspect(self) -> None:
        self._inspect_active = not self._inspect_active
        detail = self.query_one("#cluster-detail", ClusterDetailWidget)
        detail.set_inspect_mode(self._inspect_active)

        # Re-render current cluster with inspect mode
        cluster_table = self.query_one("#cluster-table", ClusterListWidget)
        if cluster_table.cursor_row is not None and cluster_table._row_labels:
            label = cluster_table._row_labels[cluster_table.cursor_row]
            cluster_data = self._cluster_index.get(label)
            if cluster_data:
                cluster_cls = self._cluster_classifications.get(label, [])
                messages = self._get_messages()
                detail.show_cluster(cluster_data, cluster_cls, messages)

        mode_str = "ON" if self._inspect_active else "OFF"
        self.notify(f"Inspect mode: {mode_str}", severity="information", timeout=2)

    def action_screen_help(self) -> None:
        recall_screen_help(self, "review")

    # --- Background workers ---

    def _check_propagation(
        self, labels: list[str], action: str, already_decided: set[int]
    ) -> None:
        """Check for propagation targets after approving clusters."""
        sender_lookup = self._get_sender_lookup()
        classifications = self.app.classifications or {}
        all_cls = list(classifications.values())
        prop_tab = self.query_one("#propagation-tab", PropagationTabWidget)

        total_suggestions = 0
        for label in labels:
            cluster_cls = self._cluster_classifications.get(label, [])
            senders = {
                sender_lookup.get(c.message_id, "")
                for c in cluster_cls
                if sender_lookup.get(c.message_id)
            }
            for sender in senders:
                suggestions = find_propagation_targets(
                    decided_sender=sender,
                    action=action,
                    all_classifications=all_cls,
                    sender_lookup=sender_lookup,
                    already_decided=already_decided,
                )
                if suggestions:
                    prop_tab.add_suggestions(suggestions)
                    total_suggestions += sum(
                        len(s.target_message_ids) for s in suggestions
                    )

        if total_suggestions > 0:
            self.notify(
                f"{total_suggestions} similar emails found. Check Propagation tab.",
                title="Propagation",
                severity="information",
                timeout=5,
            )

    @work(thread=True)
    def _run_auto_triage(self) -> None:
        """Run auto-triage in background thread."""
        classifications = self.app.classifications or {}
        sender_lookup = self._get_sender_lookup()
        all_cls = list(classifications.values())

        result = auto_triage(all_cls, sender_lookup, review_only=True)

        if result.auto_resolved_count == 0:
            self.app.call_from_thread(
                self.notify,
                "Auto-triage found no additional resolutions.",
                severity="information",
            )
            return

        # Apply auto-resolved to session
        session = self._ensure_session()
        ts = int(time.time())
        newly_decided: set[str] = set()
        for resolution in result.auto_resolved:
            label = resolution.cluster_label or "auto-resolved"
            session.decisions[label] = {
                "action": "approve",
                "message_ids": resolution.message_ids,
                "timestamp": ts,
                "auto_triage": True,
                "reason": resolution.reason,
            }
            newly_decided.add(label)

        session.auto_triage_summary = {
            "resolved_count": result.auto_resolved_count,
            "remaining_count": result.remaining_count,
            "timestamp": ts,
        }

        self.app.call_from_thread(self._save_session)

        def _update_ui() -> None:
            cluster_table = self.query_one("#cluster-table", ClusterListWidget)
            cluster_table.mark_decided(newly_decided)
            self._update_api_status()

        self.app.call_from_thread(_update_ui)
        self.app.call_from_thread(
            self.notify,
            f"Auto-triage resolved {result.auto_resolved_count} emails "
            f"({result.auto_resolved_cluster_count} groups). "
            f"{result.remaining_count} remaining.",
            title="Auto-Triage",
            severity="information",
            timeout=8,
        )

    @work(thread=True)
    def _run_api_analysis(self) -> None:
        """Submit remaining ambiguous emails to Claude Batch API."""
        remaining_count = self._get_remaining_review_count()
        if remaining_count == 0:
            self.app.call_from_thread(
                self.notify,
                "No ambiguous emails remaining.",
                severity="information",
            )
            return

        cost = estimate_api_cost(remaining_count)
        self.app.call_from_thread(
            self.notify,
            f"Submitting {remaining_count} emails. Est. cost: ${cost['estimated_cost_usd']:.4f}",
            severity="warning",
        )

        # Build payloads
        classifications = self.app.classifications or {}
        session = self.app.session
        messages = self._get_messages()
        msg_index = {m.message_id: m for m in messages}

        decided_ids: set[int] = set()
        if session:
            for label in session.decisions:
                for c in classifications.values():
                    cl = c.cluster_label or "Unclustered"
                    if c.cluster_id is None or c.cluster_id == -1:
                        cl = "Unclustered"
                    if cl == label:
                        decided_ids.add(c.message_id)
            for mid_str in session.individual_decisions:
                try:
                    decided_ids.add(int(mid_str))
                except ValueError:
                    pass

        # Collect cluster example subjects
        cluster_examples: dict[str, list[str]] = {}
        report_data = self.app.report_data or {}
        for tier_data in report_data.get("tiers", {}).values():
            for cluster in tier_data.get("clusters", []):
                cluster_examples[cluster["label"]] = cluster.get("example_subjects", [])

        payloads: list[dict] = []
        for c in classifications.values():
            if c.tier != Tier.REVIEW or c.message_id in decided_ids:
                continue
            msg = msg_index.get(c.message_id)
            if not msg:
                continue
            label = c.cluster_label or "Unclustered"
            examples = cluster_examples.get(label, [])
            payload = build_metadata_payload(c, msg, examples)
            payload["_message_id"] = c.message_id
            payloads.append(payload)

        if not payloads:
            self.app.call_from_thread(
                self.notify,
                "No payloads to submit.",
                severity="information",
            )
            return

        try:
            batch = classify_ambiguous_batch(payloads)
            batch_id = getattr(batch, "id", str(batch))
            self.app.call_from_thread(
                self.notify,
                f"Batch submitted: {batch_id}. Processing is async -- "
                "re-run TUI later to see results.",
                severity="information",
                timeout=10,
            )

            def _disable_api_btn() -> None:
                btn = self.query_one("#btn-api", Button)
                btn.disabled = True
                status = self.query_one("#api-status", Static)
                status.update(f"Batch submitted ({batch_id}). Processing...")

            self.app.call_from_thread(_disable_api_btn)

        except Exception as e:
            self.app.call_from_thread(
                self.notify,
                f"API error: {e}",
                severity="error",
            )
