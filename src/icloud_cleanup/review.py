"""Interactive review session manager with resumable state.

Provides cluster-by-cluster review walkthrough using Rich display
and questionary prompts, with auto-approve for high-confidence trash
and integration with propagation engine.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from icloud_cleanup.models import TIER_COLORS, Classification, Message, Tier

AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.98


@dataclass
class ReviewSession:
    """Persistent review session state."""

    session_id: str
    started_at: int
    last_updated: int
    version: int = 1
    auto_triage_summary: dict | None = None
    decisions: dict[str, dict] = field(default_factory=dict)
    individual_decisions: dict[str, dict] = field(default_factory=dict)
    propagation_applied: list[dict] = field(default_factory=list)
    protection_overrides: set[str] = field(default_factory=set)
    completed: bool = False


def get_session_path() -> Path:
    """Default review session file location."""
    return Path.home() / ".icloud-cleanup" / "review_session.json"


def save_session(session: ReviewSession, path: Path) -> None:
    """Serialize session to JSON with atomic write (tmp + os.replace)."""
    session.last_updated = int(time.time())
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "session_id": session.session_id,
        "version": session.version,
        "started_at": session.started_at,
        "last_updated": session.last_updated,
        "auto_triage_summary": session.auto_triage_summary,
        "decisions": session.decisions,
        "individual_decisions": session.individual_decisions,
        "propagation_applied": session.propagation_applied,
        "protection_overrides": sorted(session.protection_overrides),
        "completed": session.completed,
    }

    tmp_path = Path(str(path) + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)


def load_session(path: Path) -> ReviewSession | None:
    """Load session from JSON. Returns None if file doesn't exist."""
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    return ReviewSession(
        session_id=data["session_id"],
        version=data.get("version", 1),
        started_at=data["started_at"],
        last_updated=data["last_updated"],
        auto_triage_summary=data.get("auto_triage_summary"),
        decisions=data.get("decisions", {}),
        individual_decisions=data.get("individual_decisions", {}),
        propagation_applied=data.get("propagation_applied", []),
        protection_overrides=set(data.get("protection_overrides", [])),
        completed=data.get("completed", False),
    )


def is_auto_approvable(classifications: list[Classification]) -> bool:
    """Check if a group of classifications qualifies for trash auto-approve.

    All items must be Trash tier with confidence > 0.98.
    """
    if not classifications:
        return False
    return all(
        c.tier == Tier.TRASH and c.confidence > AUTO_APPROVE_CONFIDENCE_THRESHOLD
        for c in classifications
    )


def _cluster_key(c: Classification) -> str:
    """Normalize cluster label for grouping."""
    if c.cluster_id is None or c.cluster_id == -1:
        return "Unclustered"
    return c.cluster_label or f"cluster_{c.cluster_id}"


def _build_cluster_panel(
    label: str,
    items: list[Classification],
    messages: list[Message],
    msg_index: dict[int, Message],
) -> Panel:
    """Build a Rich Panel displaying cluster info for review."""
    from datetime import datetime

    confidences = [c.confidence for c in items]
    item_msgs = [msg_index[c.message_id] for c in items if c.message_id in msg_index]

    # Top senders
    sender_counts: dict[str, int] = {}
    for m in item_msgs:
        sender_counts[m.sender_address] = sender_counts.get(m.sender_address, 0) + 1
    top_senders = sorted(sender_counts.items(), key=lambda x: -x[1])[:3]

    # Example subjects
    subjects: list[str] = []
    seen: set[str] = set()
    for m in item_msgs:
        if m.subject not in seen:
            subjects.append(m.subject)
            seen.add(m.subject)
        if len(subjects) >= 5:
            break

    # Date range
    dates = [m.date_received for m in item_msgs if m.date_received]
    date_range_str = ""
    if dates:
        earliest = datetime.fromtimestamp(min(dates)).strftime("%b %Y")
        latest = datetime.fromtimestamp(max(dates)).strftime("%b %Y")
        date_range_str = f"{earliest} - {latest}" if earliest != latest else earliest

    table = Table(show_header=False, show_edge=False, pad_edge=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Emails", str(len(items)))
    table.add_row(
        "Confidence",
        f"{min(confidences):.2f} - {max(confidences):.2f} (avg {sum(confidences)/len(confidences):.2f})",
    )
    if date_range_str:
        table.add_row("Date range", date_range_str)
    table.add_row(
        "Top senders",
        ", ".join(f"{s} ({n})" for s, n in top_senders),
    )
    for i, subj in enumerate(subjects):
        label_str = "Subjects" if i == 0 else ""
        table.add_row(label_str, subj[:80])

    tier = items[0].tier if items else Tier.REVIEW
    color = TIER_COLORS[tier]
    return Panel(table, title=f"[cyan]{label}[/cyan] ([{color}]{tier.value}[/{color}])")


def run_review(
    remaining_classifications: list[Classification],
    messages: list[Message],
    session: ReviewSession,
    console: Console | None = None,
    session_path: Path | None = None,
    summary_lookup: dict[int, str] | None = None,
) -> ReviewSession:
    """Interactive cluster-by-cluster review with questionary prompts.

    Groups remaining classifications by cluster label, presents each
    unreviewed cluster for action. Saves session after each decision.
    Auto-approves trash clusters with confidence > 0.98.
    """
    import questionary

    from icloud_cleanup.propagation import find_propagation_targets

    console = console or Console()
    if session_path is None:
        session_path = get_session_path()

    msg_index: dict[int, Message] = {m.message_id: m for m in messages}
    sender_lookup: dict[int, str] = {m.message_id: m.sender_address for m in messages}

    # Action legend
    console.print(
        "\n[bold]Review Actions:[/bold]\n"
        "  [red]Trash all[/red]   — mark entire cluster for deletion\n"
        "  [green]Keep all[/green]   — keep all emails in cluster (no action)\n"
        "  [yellow]Skip[/yellow]       — decide later (come back on next run)\n"
        "  [cyan]Inspect[/cyan]    — review emails one by one within cluster\n"
        "  [magenta]← Back[/magenta]     — return to previous cluster\n"
    )

    # Group by cluster
    clusters: dict[str, list[Classification]] = {}
    for c in remaining_classifications:
        key = _cluster_key(c)
        clusters.setdefault(key, []).append(c)

    # Sort by size (largest first)
    sorted_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]))

    already_decided_ids: set[int] = set()
    for dec_cluster, dec_info in session.decisions.items():
        for c in remaining_classifications:
            if _cluster_key(c) == dec_cluster:
                already_decided_ids.add(c.message_id)
    for mid_str in session.individual_decisions:
        already_decided_ids.add(int(mid_str))

    idx = 0
    while idx < len(sorted_clusters):
        label, items = sorted_clusters[idx]

        # Skip already-reviewed clusters
        if label in session.decisions:
            idx += 1
            continue

        # Trash auto-approve
        if is_auto_approvable(items):
            console.print(
                f"\n[green]Auto-approved[/green] cluster [cyan]{label}[/cyan]: "
                f"{len(items)} trash items (all confidence > {AUTO_APPROVE_CONFIDENCE_THRESHOLD})"
            )
            session.decisions[label] = {
                "action": "approve",
                "timestamp": int(time.time()),
                "auto_approved": True,
            }
            save_session(session, session_path)
            idx += 1
            continue

        # Display cluster panel
        panel = _build_cluster_panel(label, items, messages, msg_index)
        console.print(panel)

        # Borderline trash notice
        if all(c.tier == Tier.TRASH for c in items):
            console.print(
                "[yellow]Note: Borderline trash cluster (confidence 0.95-0.98). "
                "Manual review recommended.[/yellow]"
            )

        # Flush console before questionary prompt
        console.file.flush() if hasattr(console, "file") else None

        position = f"[{idx + 1}/{len(sorted_clusters)}]"
        choices = ["Trash all", "Keep all", "Skip", "Inspect"]
        if idx > 0:
            choices.append("← Back")

        action = questionary.select(
            f"{position} '{label}' ({len(items)} emails) — trash, keep, or inspect?",
            choices=choices,
        ).ask()

        if action is None:
            # User pressed Ctrl-C
            console.print("\n[yellow]Review paused. Progress saved.[/yellow]")
            save_session(session, session_path)
            return session

        if action == "← Back":
            if idx > 0:
                idx -= 1
                prev_label = sorted_clusters[idx][0]
                if prev_label in session.decisions:
                    del session.decisions[prev_label]
                    for c in sorted_clusters[idx][1]:
                        session.individual_decisions.pop(str(c.message_id), None)
                    save_session(session, session_path)
            continue

        action_lower = action.lower()
        # Map new labels to internal action names
        action_map = {"trash all": "approve", "keep all": "skip"}
        internal_action = action_map.get(action_lower, action_lower)

        if internal_action == "inspect":
            from datetime import datetime

            ts = int(time.time())
            msg_idx = 0
            while msg_idx < len(items):
                c = items[msg_idx]
                msg = msg_index.get(c.message_id)
                if not msg:
                    msg_idx += 1
                    continue

                tier_color = TIER_COLORS[c.tier]
                date_str = datetime.fromtimestamp(msg.date_received).strftime("%b %d, %Y") if msg.date_received else "N/A"
                lines = [
                    f"\n  [bold]{msg.subject}[/bold]",
                    f"  From: {msg.sender_address}",
                    f"  Date: {date_str} | Tier: [{tier_color}]{c.tier.value}[/{tier_color}] | Confidence: {c.confidence:.3f}",
                ]
                if summary_lookup and c.message_id in summary_lookup:
                    snippet = summary_lookup[c.message_id][:200]
                    lines.append(f"  [dim]Preview: {snippet}[/dim]")
                if c.signals:
                    lines.append(f"  [dim]Signals: {c.signals}[/dim]")
                console.print("\n".join(lines))
                msg_choices = ["Trash", "Keep"]
                if msg_idx > 0:
                    msg_choices.append("← Back")

                per_action = questionary.select(
                    f"  [{msg_idx + 1}/{len(items)}] Trash this email or keep it?",
                    choices=msg_choices,
                ).ask()
                if per_action is None:
                    console.print("\n[yellow]Review paused. Progress saved.[/yellow]")
                    save_session(session, session_path)
                    return session
                if per_action == "← Back":
                    if msg_idx > 0:
                        msg_idx -= 1
                        prev_c = items[msg_idx]
                        session.individual_decisions.pop(str(prev_c.message_id), None)
                    continue

                per_action_map = {"trash": "approve", "keep": "skip"}
                session.individual_decisions[str(c.message_id)] = {
                    "action": per_action_map.get(per_action.lower(), per_action.lower()),
                    "timestamp": ts,
                }
                msg_idx += 1
            session.decisions[label] = {
                "action": "inspect",
                "timestamp": int(time.time()),
            }
        else:
            session.decisions[label] = {
                "action": internal_action,
                "timestamp": int(time.time()),
            }

        save_session(session, session_path)

        # Propagation suggestions after trash or reclassify
        if internal_action in ("approve", "reclassify"):
            item_senders = {
                sender_lookup.get(c.message_id, "")
                for c in items
                if sender_lookup.get(c.message_id)
            }
            for sender in item_senders:
                suggestions = find_propagation_targets(
                    decided_sender=sender,
                    action=internal_action,
                    all_classifications=remaining_classifications,
                    sender_lookup=sender_lookup,
                    already_decided=already_decided_ids,
                )
                for suggestion in suggestions:
                    console.print(
                        f"\n[magenta]Propagation suggestion:[/magenta] "
                        f"{suggestion.reason}"
                    )
                    console.print(
                        f"  Targets: {', '.join(suggestion.target_senders)} "
                        f"({len(suggestion.target_message_ids)} emails)"
                    )
                    apply = questionary.confirm(
                        f"Apply '{internal_action}' to these {len(suggestion.target_message_ids)} emails?",
                        default=False,
                    ).ask()
                    if apply:
                        ts = int(time.time())
                        for mid in suggestion.target_message_ids:
                            session.individual_decisions[str(mid)] = {
                                "action": internal_action,
                                "timestamp": ts,
                            }
                            already_decided_ids.add(mid)
                        session.propagation_applied.append({
                            "source": suggestion.source_sender,
                            "targets": suggestion.target_senders,
                            "action": internal_action,
                            "message_ids": suggestion.target_message_ids,
                        })
                        save_session(session, session_path)

        # Update already decided IDs
        for c in items:
            already_decided_ids.add(c.message_id)

        idx += 1

    session.completed = True
    save_session(session, session_path)
    return session
