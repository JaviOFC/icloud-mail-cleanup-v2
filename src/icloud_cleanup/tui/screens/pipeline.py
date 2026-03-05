"""Pipeline screen: run scan -> classify -> analyze from within the TUI."""

from __future__ import annotations

import time

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Header, ProgressBar, Static
from textual.worker import get_current_worker

from icloud_cleanup.tui.widgets.active_footer import ActiveFooter
from icloud_cleanup.tui.widgets.pipeline_log import PipelineLogWidget
from icloud_cleanup.tui.widgets.screen_help import show_screen_help_if_first_visit
from icloud_cleanup.tui.widgets.spinner import SpinnerWidget


class PipelineScreen(Screen):
    """Run the scan/classify/analyze pipeline with live progress and log output."""

    CSS_PATH = "pipeline.tcss"

    BINDINGS = [
        ("c", "cancel_pipeline", "Cancel"),
        ("escape", "switch_mode('dashboard')", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="pipeline-content"):
            yield Static(
                "Re-run the analysis pipeline: Scan -> Classify -> Content Analysis.\n"
                "This reads your Mail.app database, classifies emails by metadata signals,\n"
                "and optionally runs MLX GPU content analysis for deeper clustering.",
                id="pipeline-description",
            )
            yield Static("Pipeline: Ready", id="pipeline-status")
            with Horizontal(id="pipeline-progress-row"):
                yield ProgressBar(id="pipeline-progress", total=3, show_eta=False)
                yield SpinnerWidget(id="pipeline-spinner")
            yield PipelineLogWidget(id="pipeline-log")
            with Horizontal(id="pipeline-buttons"):
                yield Button("Run Pipeline", id="btn-pipeline", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="warning", disabled=True)
        yield ActiveFooter()

    def on_mount(self) -> None:
        show_screen_help_if_first_visit(self, "pipeline")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-pipeline":
            self.query_one("#btn-pipeline", Button).disabled = True
            self.query_one("#btn-cancel", Button).disabled = False
            self.run_pipeline()
        elif event.button.id == "btn-cancel":
            self.action_cancel_pipeline()

    @work(exclusive=True, thread=True)
    def run_pipeline(self) -> None:
        """Execute scan -> classify -> analyze in a background thread."""
        worker = get_current_worker()
        log = self.query_one("#pipeline-log", PipelineLogWidget)
        progress = self.query_one("#pipeline-progress", ProgressBar)
        status = self.query_one("#pipeline-status", Static)

        spinner = self.query_one("#pipeline-spinner", SpinnerWidget)
        self.app.call_from_thread(spinner.start)
        self.app.call_from_thread(status.update, "Pipeline: Running...")
        self.app.call_from_thread(progress.update, total=3, progress=0)

        try:
            # -- Step 1: Scan --
            self.app.call_from_thread(log.log_step, "Step 1/3: Scanning Envelope Index...")

            from icloud_cleanup.scanner import (
                get_document_attachment_message_ids,
                get_replied_conversation_ids,
                get_sender_display_names,
                get_sender_stats,
                get_sent_recipients,
                open_db,
                scan_messages,
            )

            db_path = self.app.db_path
            conn = open_db(db_path)
            try:
                messages = scan_messages(conn)
                self.app.call_from_thread(log.log_info, f"Found {len(messages):,} messages")

                if worker.is_cancelled:
                    self._finish_cancelled(log, status)
                    return

                sent_recipients = get_sent_recipients(conn)
                replied_conv_ids = get_replied_conversation_ids(conn)
                sender_stats = get_sender_stats(conn)
                sender_display_names = get_sender_display_names(conn)
                doc_msg_ids = get_document_attachment_message_ids(conn)
            finally:
                conn.close()

            # Flag document attachments
            if doc_msg_ids:
                msg_by_rowid = {m.rowid: m for m in messages}
                for rowid in doc_msg_ids:
                    if rowid in msg_by_rowid:
                        msg_by_rowid[rowid].has_document_attachment = True

            self.app.call_from_thread(
                log.log_info,
                f"Loaded {len(sent_recipients):,} sent recipients, "
                f"{len(sender_stats):,} sender stats",
            )
            self.app.call_from_thread(progress.update, progress=1)

            if worker.is_cancelled:
                self._finish_cancelled(log, status)
                return

            # -- Step 2: Classify --
            self.app.call_from_thread(log.log_step, "Step 2/3: Classifying messages...")

            from icloud_cleanup.checkpoint import load_checkpoint, save_checkpoint
            from icloud_cleanup.classifier import classify_single
            from icloud_cleanup.contacts import build_contact_profiles, load_system_contacts
            from icloud_cleanup.models import ContactProfile

            system_contacts = load_system_contacts(sent_recipients)
            profiles = build_contact_profiles(
                messages, sent_recipients, replied_conv_ids,
                system_contacts, sender_display_names,
            )
            self.app.call_from_thread(log.log_info, f"Built {len(profiles):,} contact profiles")

            if worker.is_cancelled:
                self._finish_cancelled(log, status)
                return

            now = int(time.time())
            classifications = []
            for msg in messages:
                cls = classify_single(msg, profiles, replied_conv_ids, now)
                classifications.append(cls)

            checkpoint_path = self.app.checkpoint_path
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            save_checkpoint(classifications, checkpoint_path)

            # Tier distribution
            from collections import Counter

            tier_counts = Counter(c.tier.value for c in classifications)
            tier_str = ", ".join(f"{k}: {v}" for k, v in sorted(tier_counts.items()))
            self.app.call_from_thread(log.log_info, f"Classification: {tier_str}")
            self.app.call_from_thread(log.log_info, f"Saved checkpoint: {checkpoint_path}")
            self.app.call_from_thread(progress.update, progress=2)

            if worker.is_cancelled:
                self._finish_cancelled(log, status)
                return

            # -- Step 3: Content analysis --
            self.app.call_from_thread(log.log_step, "Step 3/3: Content analysis...")
            self.app.call_from_thread(
                log.log_info,
                "This step uses MLX GPU embeddings and may take several minutes.",
            )

            try:
                self._run_content_analysis(
                    worker, log, messages, classifications, profiles,
                    replied_conv_ids, checkpoint_path,
                )
            except ImportError as e:
                self.app.call_from_thread(
                    log.log_error,
                    f"Content analysis unavailable (missing dependency: {e}). Skipping.",
                )
            except Exception as e:
                self.app.call_from_thread(
                    log.log_error,
                    f"Content analysis failed: {e}. Checkpoint from Step 2 is still valid.",
                )

            self.app.call_from_thread(progress.update, progress=3)

            if worker.is_cancelled:
                self._finish_cancelled(log, status)
                return

            # -- Reload app data --
            self._reload_app_data(log, checkpoint_path, messages)

            count = len(classifications)
            self.app.call_from_thread(
                log.log_success, f"Pipeline complete: {count} emails classified"
            )
            self.app.call_from_thread(status.update, "Pipeline: Complete")
            self.app.call_from_thread(
                self.notify, f"Pipeline complete: {count} emails classified"
            )

        except Exception as e:
            self.app.call_from_thread(log.log_error, f"Pipeline error: {e}")
            self.app.call_from_thread(status.update, "Pipeline: Error")

        finally:
            self.app.call_from_thread(spinner.stop)
            self.app.call_from_thread(
                self.query_one("#btn-pipeline", Button).__setattr__, "disabled", False
            )
            self.app.call_from_thread(
                self.query_one("#btn-cancel", Button).__setattr__, "disabled", True
            )

    def _run_content_analysis(
        self, worker, log, messages, classifications, profiles,
        replied_conv_ids, checkpoint_path,
    ) -> None:
        """Run Phase 2 content analysis (embeddings + clustering + reclassify)."""
        from collections import Counter
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from pathlib import Path

        from icloud_cleanup.checkpoint import load_checkpoint, save_checkpoint
        from icloud_cleanup.classifier import reclassify_with_content
        from icloud_cleanup.clusterer import cluster_embeddings, derive_content_scores, label_clusters
        from icloud_cleanup.embedder import batch_embed, load_embedding_model
        from icloud_cleanup.emlx_parser import build_emlx_lookup
        from icloud_cleanup.models import ContactProfile, Message
        from icloud_cleanup.scanner import ICLOUD_UUID

        mail_dir = Path.home() / "Library/Mail/V10"

        existing = load_checkpoint(checkpoint_path)
        if not existing:
            self.app.call_from_thread(log.log_error, "No checkpoint to analyze.")
            return

        msg_by_id = {m.message_id: m for m in messages}
        msg_by_rowid = {m.rowid: m for m in messages}

        # Build EMLX lookup
        emlx_lookup = build_emlx_lookup(mail_dir, ICLOUD_UUID)
        self.app.call_from_thread(
            log.log_info, f"Found {len(emlx_lookup):,} .emlx files"
        )

        if worker.is_cancelled:
            return

        # Build work items for body extraction
        work_items = []
        for msg_id, cls in existing.items():
            msg = msg_by_id.get(msg_id)
            if msg is None:
                continue
            emlx_path = emlx_lookup.get(msg.rowid)
            work_items.append((msg_id, emlx_path, msg.subject))

        # Parallel body extraction
        from icloud_cleanup.cli import _extract_body

        ordered_msg_ids = []
        texts = []
        content_sources = []

        n_workers = min(6, max(1, len(work_items)))
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(_extract_body, item): item for item in work_items}
            results_by_id = {}
            for future in as_completed(futures):
                msg_id, text, source = future.result()
                results_by_id[msg_id] = (text, source)

        for msg_id, _, _ in work_items:
            text, source = results_by_id[msg_id]
            ordered_msg_ids.append(msg_id)
            texts.append(text)
            content_sources.append(source)

        body_count = sum(1 for s in content_sources if s == "body")
        self.app.call_from_thread(
            log.log_info, f"Parsed {body_count:,} email bodies"
        )

        if worker.is_cancelled:
            return

        # Embeddings
        self.app.call_from_thread(log.log_info, "Generating embeddings (MLX GPU)...")
        model, tokenizer, model_name = load_embedding_model()
        embeddings = batch_embed(texts, model, tokenizer, model_name, batch_size=256)
        self.app.call_from_thread(
            log.log_info, f"Embeddings: {embeddings.shape}"
        )

        if worker.is_cancelled:
            return

        # Cluster
        existing_tiers = [existing[mid].tier for mid in ordered_msg_ids]
        labels = cluster_embeddings(embeddings)
        n_clusters = len(set(labels) - {-1})
        self.app.call_from_thread(log.log_info, f"Clusters: {n_clusters}")

        cluster_labels_map = label_clusters(texts, labels)
        content_scores = derive_content_scores(labels, existing_tiers)

        # Reclassify
        self.app.call_from_thread(log.log_info, "Reclassifying with fused scores...")
        updated = []
        for idx, msg_id in enumerate(ordered_msg_ids):
            cls = existing[msg_id]
            msg = msg_by_id.get(msg_id)
            if msg is None:
                updated.append(cls)
                continue

            addr = msg.sender_address.lower()
            profile = profiles.get(addr)
            if profile is None:
                profile = ContactProfile(
                    address=addr, times_sent_to=0, last_sent_to=None,
                    times_received_from=1, last_received_from=msg.date_received,
                    read_rate=0.0, reply_rate=0.0, flagged_count=0,
                    is_bidirectional=False,
                )

            c_score = content_scores.get(idx, 0.5)
            c_label_int = int(labels[idx])
            c_label_str = ", ".join(cluster_labels_map.get(c_label_int, [])) or "noise"

            new_cls = reclassify_with_content(
                classification=cls, content_score=c_score,
                cluster_id=c_label_int, cluster_label=c_label_str,
                content_source=content_sources[idx], profile=profile,
                message=msg, replied_conv_ids=replied_conv_ids,
            )
            updated.append(new_cls)

        # Include any classifications not processed
        processed_ids = set(ordered_msg_ids)
        for msg_id, cls in existing.items():
            if msg_id not in processed_ids:
                updated.append(cls)

        save_checkpoint(updated, checkpoint_path)
        self.app.call_from_thread(
            log.log_info, f"Saved {len(updated):,} reclassified items"
        )

    def _reload_app_data(self, log, checkpoint_path, messages) -> None:
        """Reload app data from the updated checkpoint."""
        from icloud_cleanup.checkpoint import load_checkpoint
        from icloud_cleanup.report import build_report_data

        checkpoint = load_checkpoint(checkpoint_path)
        self.app.classifications = checkpoint
        classifications_list = list(checkpoint.values())
        self.app.report_data = build_report_data(classifications_list, messages)
        self.app.call_from_thread(log.log_info, "App data reloaded from checkpoint")

    def _finish_cancelled(self, log, status) -> None:
        self.app.call_from_thread(log.log_error, "Pipeline cancelled by user.")
        self.app.call_from_thread(status.update, "Pipeline: Cancelled")

    def action_cancel_pipeline(self) -> None:
        """Cancel the running pipeline worker."""
        self.workers.cancel_all()
        self.notify("Cancelling pipeline...", severity="warning")
