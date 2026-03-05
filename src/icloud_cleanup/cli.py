"""CLI entry point with scan/classify/report subcommands."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from rich.console import Console

from icloud_cleanup.checkpoint import load_checkpoint, merge_checkpoint, save_checkpoint
from icloud_cleanup.classifier import classify_messages, compute_confidence, compute_signals
from icloud_cleanup.contacts import (
    build_contact_profiles,
    check_protection_override,
    is_protected,
)
from icloud_cleanup.display import (
    classify_with_progress,
    display_scan_stats,
    display_tier_summary,
    display_top_senders,
    scan_with_progress,
)
from icloud_cleanup.models import Classification, ContactProfile, Message, Tier
from icloud_cleanup.scanner import (
    get_replied_conversation_ids,
    get_sender_stats,
    get_sent_recipients,
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
        "--debug-scores",
        metavar="SENDER",
        help="Dump per-signal breakdown for a specific sender address",
    )
    classify_parser.set_defaults(func=cmd_classify)

    # report
    report_parser = subparsers.add_parser("report", help="Display classification report")
    report_parser.set_defaults(func=cmd_report)

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

        # Step 2: Build contact profiles
        console.print("[bold]Building contact profiles...[/bold]")
        sent_recipients = get_sent_recipients(conn)
        replied_conv_ids = get_replied_conversation_ids(conn)
        profiles = build_contact_profiles(messages, sent_recipients, replied_conv_ids)
        console.print(f"Built [bold]{len(profiles):,}[/bold] sender profiles\n")

        # Step 3: Check for incremental mode
        existing: dict[int, Classification] = {}
        if not args.full and args.checkpoint.exists():
            existing = load_checkpoint(args.checkpoint)
            console.print(f"Loaded [bold]{len(existing):,}[/bold] existing classifications (incremental mode)\n")

        # Step 4: Classify with progress bar
        classifications = classify_messages(messages, profiles, replied_conv_ids)

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
    """Execute the report subcommand: display checkpoint results."""
    checkpoint = load_checkpoint(args.checkpoint)
    if not checkpoint:
        console.print("[red]No checkpoint found. Run 'classify' first.[/red]")
        sys.exit(1)

    classifications = list(checkpoint.values())

    # Reload messages for sender lookup in top senders display
    conn = open_db(args.db)
    try:
        messages = scan_messages(conn)
    finally:
        conn.close()

    console.print(f"[bold]Loaded {len(classifications):,} classifications[/bold]\n")

    display_tier_summary(classifications, console=console)
    console.print()
    display_top_senders(classifications, messages, console=console)


def main() -> None:
    """Parse arguments and dispatch to subcommand handler."""
    parser = create_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")

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
