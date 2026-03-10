"""CLI entry point with scan/classify/report/review/execute subcommands."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console

from icloud_cleanup.checkpoint import load_checkpoint, merge_checkpoint, save_checkpoint
from icloud_cleanup.classifier import classify_messages, classify_single, compute_confidence, compute_signals
from icloud_cleanup.contacts import (
    build_contact_profiles,
    check_protection_override,
    is_protected,
    load_system_contacts,
)
from icloud_cleanup.display import (
    classify_with_progress,
    display_cluster_summary,
    display_reclassification_summary,
    display_scan_stats,
    display_tier_summary,
    display_top_senders,
    scan_with_progress,
)
from icloud_cleanup.models import Classification, ContactProfile, Message, Tier
from icloud_cleanup.scanner import (
    get_document_attachment_message_ids,
    get_replied_conversation_ids,
    get_sender_display_names,
    get_sender_stats,
    get_sent_recipients,
    load_summaries,
    open_db,
    scan_messages,
)

DEFAULT_CHECKPOINT = Path.home() / ".icloud-cleanup" / "checkpoint.jsonl"

console = Console()
log = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with scan/classify/report subcommands."""
    parser = argparse.ArgumentParser(
        prog="icloud_cleanup",
        description="iCloud Mail Cleanup -- Metadata Classification",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Override Envelope Index database path",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help=f"Checkpoint file path (default: {DEFAULT_CHECKPOINT})",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan and display sender statistics")
    scan_parser.set_defaults(func=cmd_scan)

    # classify
    classify_parser = subparsers.add_parser("classify", help="Run classification pipeline")
    classify_parser.add_argument(
        "--full",
        action="store_true",
        help="Force full reclassification (ignore existing checkpoint)",
    )
    classify_parser.add_argument(
        "--analyze",
        action="store_true",
        help="Also run content analysis (embeddings + clustering) after classification",
    )
    classify_parser.add_argument(
        "--debug-scores",
        metavar="SENDER",
        help="Dump per-signal breakdown for a specific sender address",
    )
    classify_parser.add_argument(
        "--mail-dir",
        type=Path,
        default=None,
        help="Override Mail V10 directory for auth header parsing",
    )
    classify_parser.set_defaults(func=cmd_classify)

    # analyze
    analyze_parser = subparsers.add_parser(
        "analyze", help="Run Phase 2 content analysis pipeline",
    )
    analyze_parser.add_argument(
        "--mail-dir",
        type=Path,
        default=None,
        help="Override Mail V10 directory (default: ~/Library/Mail/V10)",
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    # report
    report_parser = subparsers.add_parser("report", help="Display classification report")
    report_parser.add_argument(
        "--json",
        action="store_true",
        dest="export_json",
        help="Export report as JSON",
    )
    report_parser.add_argument(
        "--markdown",
        action="store_true",
        dest="export_markdown",
        help="Export report as Markdown",
    )
    report_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for exported reports",
    )
    report_parser.add_argument(
        "--format",
        choices=["terminal", "json", "markdown", "all"],
        default="terminal",
        dest="report_format",
        help="Report format (default: terminal)",
    )
    report_parser.set_defaults(func=cmd_report)

    # review
    review_parser = subparsers.add_parser(
        "review", help="Interactive review of classified emails",
    )
    review_parser.add_argument(
        "--session",
        type=Path,
        default=None,
        help="Custom review session file path",
    )
    review_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume existing review session",
    )
    review_parser.add_argument(
        "--reset",
        action="store_true",
        help="Start fresh, discard existing session",
    )
    review_parser.add_argument(
        "--web",
        action="store_true",
        help="Launch web-based review UI instead of CLI",
    )
    review_parser.set_defaults(func=cmd_review)

    # execute
    execute_parser = subparsers.add_parser(
        "execute", help="Execute approved deletions",
    )
    execute_parser.add_argument(
        "--execute",
        action="store_true",
        dest="do_execute",
        help="Actually perform deletions (default: dry-run)",
    )
    execute_parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Messages per batch (default: 100)",
    )
    execute_parser.add_argument(
        "--batch-pause",
        type=float,
        default=2.0,
        help="Seconds between batches (default: 2.0)",
    )
    execute_parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore previously deleted messages",
    )
    execute_parser.add_argument(
        "--action-log",
        type=Path,
        default=None,
        help="Custom action log path (default: ~/.icloud-cleanup/action_log.db)",
    )
    execute_parser.set_defaults(func=cmd_execute)

    # tui
    tui_parser = subparsers.add_parser(
        "tui", help="Launch interactive TUI for reviewing and managing email classifications",
    )
    tui_parser.add_argument(
        "--session", "-s",
        type=Path,
        default=None,
        help="Path to review session JSON (default: auto-detect)",
    )
    tui_parser.set_defaults(func=cmd_tui)

    return parser


def cmd_scan(args: argparse.Namespace) -> None:
    """Execute the scan subcommand: show sender volume statistics."""
    conn = open_db(args.db)
    try:
        console.print("[bold]Scanning Envelope Index...[/bold]\n")
        stats = get_sender_stats(conn)
        display_scan_stats(stats, console=console)
        total_emails = sum(d["count"] for d in stats.values())
        console.print(f"\n[bold]{total_emails:,}[/bold] emails from [bold]{len(stats):,}[/bold] unique senders")
    finally:
        conn.close()


def cmd_classify(args: argparse.Namespace) -> None:
    """Execute the classify subcommand: full scoring pipeline."""
    conn = open_db(args.db)
    try:
        # Step 1: Scan messages
        console.print("[bold]Loading messages...[/bold]")
        messages = scan_messages(conn)
        console.print(f"Found [bold]{len(messages):,}[/bold] messages\n")

        # Step 2: Load system contacts and build profiles
        console.print("[bold]Loading system contacts...[/bold]")
        sent_recipients = get_sent_recipients(conn)
        replied_conv_ids = get_replied_conversation_ids(conn)
        system_contacts = load_system_contacts(sent_recipients)
        console.print(f"Loaded [bold]{len(system_contacts.emails):,}[/bold] system contacts "
                      f"([bold]{len(system_contacts.names):,}[/bold] with names)\n")

        console.print("[bold]Building contact profiles...[/bold]")
        sender_display_names = get_sender_display_names(conn)
        profiles = build_contact_profiles(
            messages, sent_recipients, replied_conv_ids,
            system_contacts, sender_display_names,
        )
        console.print(f"Built [bold]{len(profiles):,}[/bold] sender profiles\n")

        # Step 2b: Flag document attachments
        doc_msg_ids = get_document_attachment_message_ids(conn)
        if doc_msg_ids:
            msg_rowid_map = {m.rowid: m for m in messages}
            flagged_count = 0
            for rowid in doc_msg_ids:
                if rowid in msg_rowid_map:
                    msg_rowid_map[rowid].has_document_attachment = True
                    flagged_count += 1
            console.print(f"Flagged [bold]{flagged_count:,}[/bold] messages with document attachments\n")

        # Step 2c: Extract auth headers from .emlx files
        mail_dir = getattr(args, "mail_dir", None) or Path.home() / "Library/Mail/V10"
        from icloud_cleanup.emlx_parser import build_emlx_lookup, parse_emlx_auth_headers
        from icloud_cleanup.scanner import ICLOUD_UUID

        emlx_lookup = build_emlx_lookup(mail_dir, ICLOUD_UUID)
        if emlx_lookup:
            msg_rowid_map2 = {m.rowid: m for m in messages}
            auth_count = 0
            for rowid, emlx_path in emlx_lookup.items():
                msg = msg_rowid_map2.get(rowid)
                if msg is None:
                    continue
                auth = parse_emlx_auth_headers(emlx_path)
                if auth["spam_flag"] or auth["dkim"] or auth["dmarc"] or auth["spf"]:
                    msg.spam_flag = auth["spam_flag"]
                    msg.auth_dkim = auth["dkim"]
                    msg.auth_dmarc = auth["dmarc"]
                    msg.auth_spf = auth["spf"]
                    auth_count += 1
            if auth_count:
                console.print(f"Extracted auth headers from [bold]{auth_count:,}[/bold] .emlx files\n")

        # Step 3: Check for incremental mode
        existing: dict[int, Classification] = {}
        if not args.full and args.checkpoint.exists():
            existing = load_checkpoint(args.checkpoint)
            console.print(f"Loaded [bold]{len(existing):,}[/bold] existing classifications (incremental mode)\n")

        # Step 2c: Load feedback (if available)
        from icloud_cleanup.feedback import DEFAULT_FEEDBACK_DB, FeedbackStore

        sender_feedback: dict[str, tuple[int, int]] | None = None
        if DEFAULT_FEEDBACK_DB.exists():
            fb_store = FeedbackStore(DEFAULT_FEEDBACK_DB)
            sender_feedback = fb_store.get_all()
            fb_store.close()
            if sender_feedback:
                console.print(f"Loaded feedback for [bold]{len(sender_feedback):,}[/bold] senders\n")
            else:
                sender_feedback = None

        # Step 4: Classify with progress bar
        now = int(time.time())
        classifications = classify_with_progress(
            messages, lambda msg: classify_single(msg, profiles, replied_conv_ids, now, feedback=sender_feedback)
        )

        # Step 5: Merge if incremental
        if existing:
            classifications = merge_checkpoint(existing, classifications)

        # Step 6: Save checkpoint
        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        save_checkpoint(classifications, args.checkpoint)
        console.print(f"\nCheckpoint saved: [bold]{args.checkpoint}[/bold]\n")

        # Step 7: Display summary
        display_tier_summary(classifications, console=console)

        # Step 8: Debug scores if requested
        if args.debug_scores:
            _debug_sender_scores(args.debug_scores, messages, profiles, replied_conv_ids)

    finally:
        conn.close()

    # Step 9: Chain into analyze if requested
    if args.analyze:
        console.print("\n[bold]Continuing to content analysis...[/bold]\n")
        if not hasattr(args, "mail_dir"):
            args.mail_dir = None
        cmd_analyze(args)


def _extract_body(item: tuple) -> tuple[int, str, str]:
    """Worker: parse emlx body, return (msg_id, text, source)."""
    from icloud_cleanup.emlx_parser import parse_emlx_body

    msg_id, emlx_path, subject = item
    body_text = None
    if emlx_path is not None:
        body_text = parse_emlx_body(emlx_path)
    if body_text:
        return (msg_id, body_text, "body")
    return (msg_id, subject, "subject_only")


def cmd_analyze(args: argparse.Namespace) -> None:
    """Execute the analyze subcommand: Phase 2 content analysis pipeline.

    Orchestrates: load checkpoint -> parse .emlx bodies -> embed ->
    cluster -> reclassify -> save updated checkpoint.
    """
    from collections import Counter

    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    from icloud_cleanup.classifier import reclassify_with_content
    from icloud_cleanup.clusterer import cluster_embeddings, derive_content_scores, label_clusters
    from icloud_cleanup.embedder import batch_embed, load_embedding_model
    from icloud_cleanup.emlx_parser import build_emlx_lookup, parse_emlx_body
    from icloud_cleanup.scanner import ICLOUD_UUID

    mail_dir = args.mail_dir or Path.home() / "Library/Mail/V10"

    # Step 1: Load Phase 1 checkpoint
    console.print("[bold]Step 1: Loading Phase 1 checkpoint...[/bold]")
    existing = load_checkpoint(args.checkpoint)
    if not existing:
        console.print("[red]No checkpoint found. Run 'classify' first to create Phase 1 checkpoint.[/red]")
        sys.exit(1)
    console.print(f"Loaded [bold]{len(existing):,}[/bold] classifications\n")

    # Record before-state for comparison
    before_counts: dict[Tier, int] = Counter()
    for c in existing.values():
        before_counts[c.tier] += 1

    # Load messages from DB for ROWID mapping + profiles for reclassification
    conn = open_db(args.db)
    try:
        console.print("[bold]Loading messages and profiles...[/bold]")
        messages = scan_messages(conn)
        msg_by_id: dict[int, Message] = {m.message_id: m for m in messages}
        msg_by_rowid: dict[int, Message] = {m.rowid: m for m in messages}

        sent_recipients = get_sent_recipients(conn)
        replied_conv_ids = get_replied_conversation_ids(conn)
        system_contacts = load_system_contacts(sent_recipients)
        sender_display_names = get_sender_display_names(conn)
        profiles = build_contact_profiles(
            messages, sent_recipients, replied_conv_ids,
            system_contacts, sender_display_names,
        )

        # Flag document attachments
        doc_msg_ids = get_document_attachment_message_ids(conn)
        if doc_msg_ids:
            for rowid in doc_msg_ids:
                if rowid in msg_by_rowid:
                    msg_by_rowid[rowid].has_document_attachment = True

        console.print(f"  Messages: [bold]{len(messages):,}[/bold], "
                      f"Profiles: [bold]{len(profiles):,}[/bold]\n")
    finally:
        conn.close()

    # Step 2: Build EMLX lookup and extract bodies
    console.print("[bold]Step 2: Extracting email bodies from .emlx files...[/bold]")
    emlx_lookup = build_emlx_lookup(mail_dir, ICLOUD_UUID)
    console.print(f"  Found [bold]{len(emlx_lookup):,}[/bold] .emlx files on disk\n")

    # Build work items: (msg_id, emlx_path_or_None, subject)
    work_items: list[tuple[int, Path | None, str]] = []
    for msg_id, cls in existing.items():
        msg = msg_by_id.get(msg_id)
        if msg is None:
            continue
        emlx_path = emlx_lookup.get(msg.rowid)
        work_items.append((msg_id, emlx_path, msg.subject))

    # Parallel body extraction using multiprocessing (6 workers on M1 Max)

    ordered_msg_ids: list[int] = []
    texts: list[str] = []
    content_sources: list[str] = []

    n_workers = min(6, len(work_items))
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing bodies...", total=len(work_items))
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(_extract_body, item): item for item in work_items}
            results_by_id: dict[int, tuple[str, str]] = {}
            for future in as_completed(futures):
                msg_id, text, source = future.result()
                results_by_id[msg_id] = (text, source)
                progress.advance(task)

    # Preserve original checkpoint order
    for msg_id, _, _ in work_items:
        text, source = results_by_id[msg_id]
        ordered_msg_ids.append(msg_id)
        texts.append(text)
        content_sources.append(source)

    body_count = sum(1 for s in content_sources if s == "body")
    subj_count = sum(1 for s in content_sources if s == "subject_only")
    console.print(f"  Parsed: [bold]{body_count:,}[/bold] bodies, "
                  f"[bold]{subj_count:,}[/bold] subject-only fallbacks "
                  f"({n_workers} workers)\n")

    # Step 3: Generate embeddings
    console.print("[bold]Step 3: Generating embeddings (MLX GPU)...[/bold]")
    model, tokenizer, model_name = load_embedding_model()
    console.print(f"  Model: [bold]{model_name}[/bold]")

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                   BarColumn(), MofNCompleteColumn(),
                   TimeElapsedColumn(), console=console) as progress:
        embed_task = progress.add_task("Embedding...", total=len(texts))
        embeddings = batch_embed(
            texts, model, tokenizer, model_name,
            batch_size=256,
            progress_callback=lambda n: progress.advance(embed_task, n),
        )
    console.print(f"  Embeddings: [bold]{embeddings.shape}[/bold]\n")

    # Step 4: Cluster and label
    console.print("[bold]Step 4: Clustering embeddings...[/bold]")
    existing_tiers = [existing[mid].tier for mid in ordered_msg_ids]
    labels = cluster_embeddings(embeddings)

    n_clusters = len(set(labels) - {-1})
    noise_count = int((labels == -1).sum())
    noise_pct = noise_count / len(labels) * 100 if len(labels) > 0 else 0
    console.print(f"  Clusters: [bold]{n_clusters}[/bold], "
                  f"Noise: [bold]{noise_count:,}[/bold] ({noise_pct:.1f}%)\n")

    cluster_labels_map = label_clusters(texts, labels)
    content_scores = derive_content_scores(labels, existing_tiers)

    # Build cluster size map for display
    cluster_sizes: dict[int, int] = Counter()
    for lbl in labels:
        if lbl != -1:
            cluster_sizes[int(lbl)] += 1

    display_cluster_summary(cluster_labels_map, cluster_sizes, console=console)
    console.print()

    # Step 5: Reclassify
    console.print("[bold]Step 5: Reclassifying with fused scores...[/bold]")
    updated_classifications: list[Classification] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Reclassifying...", total=len(ordered_msg_ids))
        for idx, msg_id in enumerate(ordered_msg_ids):
            cls = existing[msg_id]
            msg = msg_by_id.get(msg_id)
            if msg is None:
                updated_classifications.append(cls)
                progress.advance(task)
                continue

            addr = msg.sender_address.lower()
            profile = profiles.get(addr)
            if profile is None:
                profile = ContactProfile(
                    address=addr,
                    times_sent_to=0,
                    last_sent_to=None,
                    times_received_from=1,
                    last_received_from=msg.date_received,
                    read_rate=0.0,
                    reply_rate=0.0,
                    flagged_count=0,
                    is_bidirectional=False,
                )

            c_score = content_scores.get(idx, 0.5)
            c_label_int = int(labels[idx])
            c_label_str = ", ".join(cluster_labels_map.get(c_label_int, [])) or "noise"

            new_cls = reclassify_with_content(
                classification=cls,
                content_score=c_score,
                cluster_id=c_label_int,
                cluster_label=c_label_str,
                content_source=content_sources[idx],
                profile=profile,
                message=msg,
                replied_conv_ids=replied_conv_ids,
            )
            updated_classifications.append(new_cls)
            progress.advance(task)

    # Also include any classifications not in ordered_msg_ids (no matching message)
    processed_ids = set(ordered_msg_ids)
    for msg_id, cls in existing.items():
        if msg_id not in processed_ids:
            updated_classifications.append(cls)

    # Step 6: Save and report
    console.print("\n[bold]Step 6: Saving updated checkpoint...[/bold]")
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    save_checkpoint(updated_classifications, args.checkpoint)
    console.print(f"  Saved [bold]{len(updated_classifications):,}[/bold] classifications to {args.checkpoint}\n")

    # After counts
    after_counts: dict[Tier, int] = Counter()
    for c in updated_classifications:
        after_counts[c.tier] += 1

    display_reclassification_summary(before_counts, after_counts, console=console)
    console.print()
    display_tier_summary(updated_classifications, console=console)


def _debug_sender_scores(
    sender: str,
    messages: list[Message],
    profiles: dict[str, ContactProfile],
    replied_conv_ids: set[int],
) -> None:
    """Dump per-signal breakdown for a specific sender's messages."""
    sender_lower = sender.lower()
    sender_msgs = [m for m in messages if m.sender_address.lower() == sender_lower]

    if not sender_msgs:
        console.print(f"\n[red]No messages found from sender: {sender}[/red]")
        return

    profile = profiles.get(sender_lower)
    if profile is None:
        console.print(f"\n[red]No profile found for sender: {sender}[/red]")
        return

    console.print(f"\n[bold]Debug scores for: {sender}[/bold]")
    console.print(f"Profile: sent_to={profile.times_sent_to}, received={profile.times_received_from}, "
                  f"read_rate={profile.read_rate:.2f}, reply_rate={profile.reply_rate:.2f}, "
                  f"bidirectional={profile.is_bidirectional}")
    console.print(f"Messages from sender: {len(sender_msgs)}\n")

    for i, msg in enumerate(sender_msgs[:10], 1):
        signals = compute_signals(msg, profile)
        confidence, explanation = compute_confidence(signals)
        protected = is_protected(msg, profile, replied_conv_ids)
        overridden = check_protection_override(profile) if protected else False

        console.print(f"[bold]Message {i}[/bold] (id={msg.message_id}, subject={msg.subject[:60]})")
        console.print(f"  Protected: {protected}, Overridden: {overridden}")
        for s in signals:
            console.print(f"  {s.name:25s} value={s.value:.3f}  weight={s.weight:.2f}  | {s.explanation}")
        console.print(f"  [bold]Confidence: {confidence:.4f}[/bold]")
        console.print()

    if len(sender_msgs) > 10:
        console.print(f"  ... and {len(sender_msgs) - 10} more messages (showing first 10)")


def cmd_report(args: argparse.Namespace) -> None:
    """Execute the report subcommand: display checkpoint results with optional export."""
    from icloud_cleanup.report import generate_report

    checkpoint = load_checkpoint(args.checkpoint)
    if not checkpoint:
        console.print("[red]No checkpoint found. Run 'classify' first.[/red]")
        sys.exit(1)

    classifications = list(checkpoint.values())

    conn = open_db(args.db)
    try:
        messages = scan_messages(conn)
    finally:
        conn.close()

    console.print(f"[bold]Loaded {len(classifications):,} classifications[/bold]\n")

    # Determine effective format from flags
    fmt = args.report_format
    if args.export_json and fmt == "terminal":
        fmt = "json"
    elif args.export_markdown and fmt == "terminal":
        fmt = "markdown"

    output_dir = args.output or (Path.home() / ".icloud-cleanup" / "reports")

    if fmt == "terminal":
        display_tier_summary(classifications, console=console)
        console.print()
        display_top_senders(classifications, messages, console=console)
    else:
        result = generate_report(classifications, messages, output_dir, format=fmt)
        for fmt_name, path in result.items():
            if path != "rendered":
                console.print(f"[green]Exported {fmt_name}:[/green] {path}")


def cmd_review(args: argparse.Namespace) -> None:
    """Execute the review subcommand: interactive review of classified emails."""
    if args.web:
        from icloud_cleanup.review import get_session_path
        from icloud_cleanup.web.server import launch

        session_path = args.session or get_session_path()
        launch(
            checkpoint_path=args.checkpoint,
            session_path=session_path,
            db_path=args.db,
        )
        return

    import questionary

    from icloud_cleanup.auto_triage import auto_triage
    from icloud_cleanup.review import (
        ReviewSession,
        get_session_path,
        load_session,
        run_review,
        save_session,
    )

    checkpoint = load_checkpoint(args.checkpoint)
    if not checkpoint:
        console.print("[red]No checkpoint found. Run 'classify' first.[/red]")
        sys.exit(1)

    classifications = list(checkpoint.values())

    conn = open_db(args.db)
    try:
        messages = scan_messages(conn)
        summaries = load_summaries(conn)
    finally:
        conn.close()

    msg_index: dict[int, Message] = {m.message_id: m for m in messages}
    sender_lookup: dict[int, str] = {m.message_id: m.sender_address for m in messages}

    console.print(f"[bold]Loaded {len(classifications):,} classifications[/bold]")
    if summaries:
        console.print(f"[bold]Loaded {len(summaries):,} email summaries[/bold]")
    console.print()

    # Session management
    session_path = args.session or get_session_path()

    if args.reset and session_path.exists():
        session_path.unlink()
        console.print("[yellow]Previous session discarded.[/yellow]\n")

    session = None
    if args.resume or (not args.reset and session_path.exists()):
        session = load_session(session_path)
        if session:
            console.print(
                f"[green]Resuming session[/green] {session.session_id} "
                f"({len(session.decisions)} clusters reviewed)\n"
            )

    if session is None:
        session = ReviewSession(
            session_id=f"review_{time.strftime('%Y%m%d_%H%M%S')}",
            started_at=int(time.time()),
            last_updated=int(time.time()),
        )

    # Auto-triage pass on Review-tier items
    console.print("[bold]Running auto-triage...[/bold]")
    triage_result = auto_triage(classifications, sender_lookup)

    console.print(
        f"  Auto-resolved: [green]{triage_result.auto_resolved_count:,}[/green] emails "
        f"across [green]{triage_result.auto_resolved_cluster_count}[/green] groups\n"
        f"  Remaining for review: [yellow]{triage_result.remaining_count:,}[/yellow] emails "
        f"in [yellow]{triage_result.remaining_cluster_count}[/yellow] clusters\n"
    )

    session.auto_triage_summary = {
        "auto_resolved_count": triage_result.auto_resolved_count,
        "auto_resolved_cluster_count": triage_result.auto_resolved_cluster_count,
        "remaining_count": triage_result.remaining_count,
        "remaining_cluster_count": triage_result.remaining_cluster_count,
    }

    # Offer inspection of auto-resolved items
    if triage_result.auto_resolved:
        inspect = questionary.confirm(
            "Inspect auto-resolved items?", default=False,
        ).ask()
        if inspect:
            for resolution in triage_result.auto_resolved:
                console.print(
                    f"  {resolution.reason} "
                    f"({len(resolution.message_ids)} emails, "
                    f"avg confidence {resolution.avg_confidence:.2f})"
                )

    # Run interactive review on remaining items
    if triage_result.remaining:
        session = run_review(
            triage_result.remaining,
            messages,
            session,
            console=console,
            session_path=session_path,
            summary_lookup=summaries or None,
        )

    # Summary
    approve_count = sum(
        1 for d in session.decisions.values() if d.get("action") == "approve"
    )
    skip_count = sum(
        1 for d in session.decisions.values() if d.get("action") == "skip"
    )
    reclassify_count = sum(
        1 for d in session.decisions.values() if d.get("action") == "reclassify"
    )
    console.print(f"\n[bold]Review summary:[/bold]")
    console.print(f"  Approved for deletion: [red]{approve_count}[/red] clusters")
    console.print(f"  Skipped: [green]{skip_count}[/green] clusters")
    console.print(f"  Reclassified: [yellow]{reclassify_count}[/yellow] clusters")

    # Suggest API fallback for remaining ambiguous items
    remaining_ambiguous = [
        c for c in triage_result.remaining
        if c.tier == Tier.REVIEW
        and str(c.message_id) not in session.individual_decisions
        and all(
            _cluster_key_for_cls(c) != k
            for k in session.decisions
            if session.decisions[k].get("action") in ("approve", "reclassify")
        )
    ]

    if remaining_ambiguous:
        from icloud_cleanup.api_fallback import estimate_api_cost

        cost = estimate_api_cost(len(remaining_ambiguous))
        console.print(
            f"\n[bold]{len(remaining_ambiguous)}[/bold] emails remain ambiguous. "
            f"Claude API analysis estimated cost: [bold]${cost['estimated_cost_usd']:.4f}[/bold]"
        )
        use_api = questionary.confirm(
            "Run Claude API analysis on ambiguous emails?", default=False,
        ).ask()
        if use_api:
            from icloud_cleanup.api_fallback import (
                build_metadata_payload,
                classify_ambiguous_batch,
                integrate_api_results,
            )

            payloads = []
            for c in remaining_ambiguous:
                msg = msg_index.get(c.message_id)
                if msg is None:
                    continue
                cluster_examples = [
                    msg_index[oc.message_id].subject
                    for oc in classifications
                    if oc.cluster_id == c.cluster_id
                    and oc.message_id in msg_index
                ][:5]
                payload = build_metadata_payload(c, msg, cluster_examples)
                payload["_message_id"] = c.message_id
                payloads.append(payload)

            if payloads:
                console.print(f"Submitting {len(payloads)} emails to Claude API...")
                try:
                    batch = classify_ambiguous_batch(payloads)
                    console.print(f"Batch submitted: {batch.id}")
                    console.print(
                        "[yellow]Batch processing is async. "
                        "Check results later and re-run review.[/yellow]"
                    )
                except Exception as e:
                    console.print(f"[red]API error: {e}[/red]")

    save_session(session, session_path)
    console.print(f"\nSession saved: [bold]{session_path}[/bold]")


def _cluster_key_for_cls(c: Classification) -> str:
    """Normalize cluster label for lookup."""
    if c.cluster_id is None or c.cluster_id == -1:
        return "Unclustered"
    return c.cluster_label or f"cluster_{c.cluster_id}"


def cmd_execute(args: argparse.Namespace) -> None:
    """Execute the execute subcommand: carry out approved deletions."""
    from icloud_cleanup.executor import ActionLog, execute_deletions, restore_from_log
    from icloud_cleanup.review import get_session_path, load_session

    # Load review session
    session_path = get_session_path()
    session = load_session(session_path)
    if session is None and not args.restore:
        console.print("[red]No review session found. Run 'review' first.[/red]")
        sys.exit(1)

    action_log_path = args.action_log or (Path.home() / ".icloud-cleanup" / "action_log.db")
    action_log = ActionLog(action_log_path)

    try:
        if args.restore:
            from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

            restorable = action_log.get_restorable()
            console.print(f"[bold]Restoring {len(restorable)} previously deleted messages...[/bold]\n")

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold]{task.description}"),
                MofNCompleteColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Restoring...", total=len(restorable))
                result = restore_from_log(
                    action_log,
                    dry_run=not args.do_execute,
                    batch_size=args.batch_size,
                    batch_pause=args.batch_pause,
                    progress_callback=lambda n: progress.advance(task, n),
                )

            console.print(f"  Restored: [green]{result['success_count']}[/green]")
            console.print(f"  Errors: [red]{result['error_count']}[/red]")
            if not args.do_execute:
                console.print(
                    "\n[yellow]Dry-run mode. Run with --execute to carry out restores.[/yellow]"
                )
            return

        # Collect approved message IDs from session
        checkpoint = load_checkpoint(args.checkpoint)
        if not checkpoint:
            console.print("[red]No checkpoint found.[/red]")
            sys.exit(1)

        approved_ids: set[int] = set()

        # From cluster-level approve decisions
        all_classifications = list(checkpoint.values())
        for cluster_key, decision in session.decisions.items():
            if decision.get("action") == "approve":
                for c in all_classifications:
                    if _cluster_key_for_cls(c) == cluster_key:
                        approved_ids.add(c.message_id)

        # From individual decisions (split, inspect, propagation)
        for mid_str, decision in session.individual_decisions.items():
            if decision.get("action") == "approve":
                approved_ids.add(int(mid_str))

        if not approved_ids:
            console.print("[yellow]No approved items to execute.[/yellow]")
            return

        # Load messages for approved items
        conn = open_db(args.db)
        try:
            messages = scan_messages(conn)
        finally:
            conn.close()

        approved_messages = [m for m in messages if m.message_id in approved_ids]
        approved_classifications = {
            c.message_id: c
            for c in all_classifications
            if c.message_id in approved_ids
        }

        from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

        dry_run = not args.do_execute
        mode_str = "[yellow]DRY-RUN[/yellow]" if dry_run else "[red]LIVE[/red]"

        # Check how many were already executed in prior runs
        already_done = action_log.get_executed_message_ids()
        new_count = sum(1 for m in approved_messages if m.message_id not in already_done)
        console.print(f"[bold]Executing deletions ({mode_str})...[/bold]")
        if len(already_done & {m.message_id for m in approved_messages}) > 0:
            console.print(f"  Approved: [bold]{len(approved_messages)}[/bold] messages "
                         f"([bold]{new_count}[/bold] new, "
                         f"[dim]{len(approved_messages) - new_count} already executed[/dim])\n")
        else:
            console.print(f"  Approved: [bold]{len(approved_messages)}[/bold] messages\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Executing...", total=len(approved_messages))
            overrides = {int(mid) for mid in session.protection_overrides} if session.protection_overrides else None
            result = execute_deletions(
                approved_messages,
                approved_classifications,
                action_log,
                dry_run=dry_run,
                batch_size=args.batch_size,
                batch_pause=args.batch_pause,
                progress_callback=lambda n: progress.advance(task, n),
                protection_overrides=overrides,
            )

        console.print(f"\n[bold]Execution results:[/bold]")
        console.print(f"  Moved to trash: [green]{result['success_count']}[/green]")
        console.print(f"  Errors: [red]{result['error_count']}[/red]")
        console.print(f"  Skipped (protected): [yellow]{result['skipped_protected']}[/yellow]")
        if result.get('already_executed', 0) > 0:
            console.print(f"  Already executed (prior run): [dim]{result['already_executed']}[/dim]")
        if result.get('overridden_count', 0) > 0:
            console.print(f"  Overridden (protected→deleted): [cyan]{result['overridden_count']}[/cyan]")

        if result["errors"]:
            console.print("\n[red]Errors:[/red]")
            for err in result["errors"][:10]:
                console.print(f"  {err}")

        if dry_run:
            console.print(
                "\n[yellow]Dry-run mode. Run with --execute to carry out deletions.[/yellow]"
            )
        else:
            # Record feedback for future classification runs
            from icloud_cleanup.feedback import FeedbackStore

            fb_items: list[tuple[str, str]] = []
            for msg in approved_messages:
                cls = approved_classifications.get(msg.message_id)
                if cls is None:
                    continue
                action = "trash" if cls.tier == Tier.TRASH else "keep"
                fb_items.append((msg.sender_address, action))

            # Also record keeps from session (items reviewed but not approved)
            conn2 = open_db(args.db)
            try:
                all_msgs = scan_messages(conn2)
            finally:
                conn2.close()
            msg_addr = {m.message_id: m.sender_address for m in all_msgs}
            for mid_str, decision in session.individual_decisions.items():
                mid = int(mid_str)
                if decision.get("action") == "skip" and mid not in approved_ids:
                    addr = msg_addr.get(mid)
                    if addr:
                        fb_items.append((addr, "keep"))

            if fb_items:
                fb_store = FeedbackStore()
                fb_store.record_batch(fb_items)
                fb_store.close()
                console.print(f"\nRecorded feedback for [bold]{len(fb_items):,}[/bold] senders")
    finally:
        action_log.close()


def cmd_tui(args: argparse.Namespace) -> None:
    """Launch the interactive Textual TUI."""
    checkpoint_path = args.checkpoint
    if not checkpoint_path.exists():
        console.print(f"[red]Checkpoint not found: {checkpoint_path}[/red]")
        console.print("Run 'classify' first to create a checkpoint.")
        sys.exit(1)

    session_path = args.session
    if session_path is None:
        from icloud_cleanup.review import get_session_path

        session_path = get_session_path()

    # Auto-discover DB if not specified so inspect mode and real sender data work
    db_path = args.db
    if db_path is None:
        from icloud_cleanup.scanner import ENVELOPE_INDEX

        if ENVELOPE_INDEX.exists():
            db_path = ENVELOPE_INDEX

    # Lazy import to avoid textual overhead for non-TUI commands
    from icloud_cleanup.tui import CleanupApp

    app = CleanupApp(
        checkpoint_path=checkpoint_path,
        session_path=session_path,
        db_path=db_path,
        show_welcome=True,
    )
    app.run()


def main() -> None:
    """Parse arguments and dispatch to subcommand handler."""
    parser = create_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
        # Suppress noisy HTTP library logs even in verbose mode
        for noisy in ("httpcore", "httpx", "filelock", "urllib3"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except FileNotFoundError as e:
        console.print(f"\n[red]File not found: {e}[/red]")
        console.print("Make sure the Envelope Index exists or use --db to specify its path.")
        sys.exit(1)
