"""FastAPI web server for interactive email review.

Serves a local-only web UI for browsing, filtering, and making
trash/keep decisions on classified emails. Reads checkpoint.jsonl
and writes review_session.json — fully interoperable with the CLI pipeline.
"""

from __future__ import annotations

import logging
import time
import webbrowser
from collections import defaultdict
from pathlib import Path
from statistics import mean

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from icloud_cleanup.checkpoint import load_checkpoint
from icloud_cleanup.models import Classification, Message, Tier
from icloud_cleanup.review import ReviewSession, load_session, save_session

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="iCloud Mail Cleanup Review")

# --- Module-level state (set by launch()) ---
_checkpoint: dict[int, Classification] = {}
_classifications: list[Classification] = []
_messages: list[Message] = []
_msg_index: dict[int, Message] = {}
_sender_lookup: dict[int, str] = {}
_session: ReviewSession | None = None
_session_path: Path = Path.home() / ".icloud-cleanup" / "review_session.json"
_db_path: Path | None = None
_emlx_lookup: dict[int, Path] = {}
_summaries: dict[int, str] = {}
_executed_ids: set[int] = set()


# --- Pydantic models ---

class DecideRequest(BaseModel):
    message_ids: list[str]
    action: str  # "trash" or "keep"


class DecideClusterRequest(BaseModel):
    cluster_label: str
    action: str  # "approve", "reject", "skip"


# --- Helpers ---

def _cluster_key(c: Classification) -> str:
    if c.cluster_id is None or c.cluster_id == -1:
        return "Unclustered"
    return c.cluster_label or f"cluster_{c.cluster_id}"


def _get_session() -> ReviewSession:
    global _session
    if _session is None:
        _session = ReviewSession(
            session_id=f"web_{time.strftime('%Y%m%d_%H%M%S')}",
            started_at=int(time.time()),
            last_updated=int(time.time()),
        )
    return _session


def _save():
    save_session(_get_session(), _session_path)


def _msg_to_dict(msg: Message, cls: Classification) -> dict:
    return {
        "message_id": str(msg.message_id),
        "sender": msg.sender_address,
        "domain": msg.sender_address.split("@")[1] if "@" in msg.sender_address else "",
        "subject": msg.subject,
        "date": msg.date_received,
        "tier": cls.tier.value,
        "confidence": round(cls.confidence, 4),
        "cluster_label": _cluster_key(cls),
        "protected": cls.protected,
        "signals": cls.signals,
    }


# --- Routes ---

@app.get("/")
async def serve_index():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/clusters")
async def get_clusters():
    """Cluster summaries with size, confidence range, top senders, decision status."""
    session = _get_session()
    clusters: dict[str, list[Classification]] = defaultdict(list)
    for c in _classifications:
        clusters[_cluster_key(c)].append(c)

    result = []
    for label, items in sorted(clusters.items(), key=lambda x: -len(x[1])):
        confs = [c.confidence for c in items]
        # Top senders
        sender_counts: dict[str, int] = defaultdict(int)
        for c in items:
            msg = _msg_index.get(c.message_id)
            if msg:
                sender_counts[msg.sender_address] += 1
        top_senders = sorted(sender_counts.items(), key=lambda x: -x[1])[:3]

        # Decision status: count individual decisions within this cluster
        cluster_decision = session.decisions.get(label)
        individual_decided = 0
        individual_trash = 0
        individual_keep = 0
        for c in items:
            mid = str(c.message_id)
            if mid in session.individual_decisions:
                individual_decided += 1
                act = session.individual_decisions[mid].get("action")
                if act == "approve":
                    individual_trash += 1
                elif act == "skip":
                    individual_keep += 1

        # Effective decided count: cluster decision covers all, otherwise individual
        if cluster_decision:
            decided_count = len(items)
        else:
            decided_count = individual_decided

        result.append({
            "label": label,
            "count": len(items),
            "confidence_min": round(min(confs), 3),
            "confidence_max": round(max(confs), 3),
            "confidence_avg": round(mean(confs), 3),
            "top_senders": [{"sender": s, "count": n} for s, n in top_senders],
            "tier_breakdown": {t.value: 0 for t in Tier} | {
                t.value: sum(1 for c in items if c.tier == t) for t in Tier
            },
            "decision": cluster_decision.get("action") if cluster_decision else None,
            "decided_count": decided_count,
            "individual_trash": individual_trash,
            "individual_keep": individual_keep,
        })
    return result


def _resolve_decision(c: Classification, session: ReviewSession) -> str | None:
    """Resolve effective decision for a classification."""
    mid = str(c.message_id)
    if mid in session.individual_decisions:
        return session.individual_decisions[mid].get("action")
    cluster_dec = session.decisions.get(_cluster_key(c))
    if cluster_dec:
        return cluster_dec.get("action")
    return None


@app.get("/api/emails")
async def get_emails(
    cluster: str | None = Query(None),
    tier: str | None = Query(None),
    sender: str | None = Query(None),
    q: str | None = Query(None),
    confidence_min: float | None = Query(None),
    confidence_max: float | None = Query(None),
    decision: str | None = Query(None),
    sort_by: str | None = Query(None),
    sort_dir: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    hide_executed: bool = Query(False),
):
    """Paginated, filterable email list.

    decision filter: "approve" (marked for deletion), "skip" (marked keep),
    "pending" (no decision yet).
    """
    session = _get_session()
    filtered: list[tuple[Message, Classification, str | None]] = []

    for c in _classifications:
        msg = _msg_index.get(c.message_id)
        if msg is None:
            continue
        if hide_executed and c.message_id in _executed_ids:
            continue

        if cluster and _cluster_key(c) != cluster:
            continue
        if tier and c.tier.value != tier:
            continue
        if sender:
            if "@" in sender:
                if msg.sender_address.lower() != sender.lower():
                    continue
            else:
                domain = msg.sender_address.split("@")[1] if "@" in msg.sender_address else ""
                if domain.lower() != sender.lower():
                    continue
        if q:
            q_lower = q.lower()
            if q_lower not in msg.subject.lower() and q_lower not in msg.sender_address.lower():
                continue
        if confidence_min is not None and c.confidence < confidence_min:
            continue
        if confidence_max is not None and c.confidence > confidence_max:
            continue

        dec = _resolve_decision(c, session)

        if decision:
            if decision == "pending" and dec is not None:
                continue
            elif decision != "pending" and dec != decision:
                continue

        filtered.append((msg, c, dec))

    # Dynamic sort
    sort_field = sort_by if sort_by in ("sender", "subject", "date", "tier", "confidence") else "date"
    reverse = sort_dir != "asc"
    sort_keys = {
        "sender": lambda x: x[0].sender_address.lower(),
        "subject": lambda x: x[0].subject.lower(),
        "date": lambda x: x[0].date_received or 0,
        "tier": lambda x: x[1].tier.value,
        "confidence": lambda x: x[1].confidence,
    }
    filtered.sort(key=sort_keys[sort_field], reverse=reverse)

    total = len(filtered)
    start = (page - 1) * per_page
    page_items = filtered[start : start + per_page]

    emails = []
    for msg, c, dec in page_items:
        d = _msg_to_dict(msg, c)
        d["decision"] = dec
        emails.append(d)

    # Unique domains in current filtered set for domain filter dropdown
    domains: dict[str, int] = defaultdict(int)
    for msg, c, _ in filtered:
        domain = msg.sender_address.split("@")[1] if "@" in msg.sender_address else ""
        if domain:
            domains[domain] += 1
    top_domains = sorted(domains.items(), key=lambda x: -x[1])[:30]

    # Decision counts for the current filter set (excluding decision filter)
    all_decisions = [_resolve_decision(c, session) for c in _classifications if _msg_index.get(c.message_id)]
    decision_counts = {
        "pending": sum(1 for d in all_decisions if d is None),
        "approve": sum(1 for d in all_decisions if d == "approve"),
        "skip": sum(1 for d in all_decisions if d == "skip"),
    }

    # Compute avg confidence across all filtered results
    all_confs = [c.confidence for _, c, _ in filtered]
    avg_conf = round(mean(all_confs), 4) if all_confs else 0

    # Top domain across all filtered results
    top_domain = top_domains[0][0] if top_domains else None
    top_domain_count = top_domains[0][1] if top_domains else 0

    return {
        "emails": emails,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "domains": [{"domain": d, "count": n} for d, n in top_domains],
        "decision_counts": decision_counts,
        "avg_confidence": avg_conf,
        "top_domain": top_domain,
        "top_domain_count": top_domain_count,
        "executed_count": len(_executed_ids),
    }


@app.get("/api/email/{message_id}/body")
async def get_email_body(message_id: str):
    """Lazy-load email body snippet from .emlx file, with summary fallback."""
    mid_int = int(message_id)
    msg = _msg_index.get(mid_int)
    if msg is None:
        return JSONResponse({"error": "Message not found"}, status_code=404)

    cls = _checkpoint.get(mid_int)

    # Try .emlx body first
    body = None
    source = None
    if _emlx_lookup and msg.rowid in _emlx_lookup:
        from icloud_cleanup.emlx_parser import parse_emlx_body
        body = parse_emlx_body(_emlx_lookup[msg.rowid], max_chars=500)
        if body:
            source = "emlx"

    # Fallback: Apple Intelligence summary from DB
    if not body and mid_int in _summaries:
        body = _summaries[mid_int]
        source = "summary"

    return {
        "message_id": message_id,
        "body": body,
        "source": source,
        "signals": cls.signals if cls else None,
        "content_score": cls.content_score if cls else None,
        "cluster_label": cls.cluster_label if cls else None,
    }


@app.post("/api/decide")
async def decide(req: DecideRequest):
    """Record trash/keep decisions for individual messages."""
    session = _get_session()
    action_map = {"trash": "approve", "keep": "skip"}
    internal = action_map.get(req.action, req.action)
    ts = int(time.time())

    for mid in req.message_ids:
        session.individual_decisions[str(mid)] = {
            "action": internal,
            "timestamp": ts,
        }

    _save()
    return {"status": "ok", "decided": len(req.message_ids)}


class DecideSenderRequest(BaseModel):
    key: str
    group_by: str  # "domain" or "sender"
    action: str  # "trash" or "keep"


class DecideRemainingRequest(BaseModel):
    pass


class OverrideProtectionRequest(BaseModel):
    message_ids: list[str]
    override: bool = True


@app.post("/api/decide-sender")
async def decide_sender(req: DecideSenderRequest):
    """Bulk-decide all emails matching a sender address or domain."""
    session = _get_session()
    action_map = {"trash": "approve", "keep": "skip"}
    internal = action_map.get(req.action, req.action)
    ts = int(time.time())
    decided = 0

    for c in _classifications:
        msg = _msg_index.get(c.message_id)
        if msg is None:
            continue
        if req.group_by == "sender":
            match = msg.sender_address.lower() == req.key.lower()
        else:
            domain = msg.sender_address.split("@")[1].lower() if "@" in msg.sender_address else ""
            match = domain == req.key.lower()
        if match:
            session.individual_decisions[str(c.message_id)] = {
                "action": internal,
                "timestamp": ts,
            }
            decided += 1

    _save()
    return {"status": "ok", "decided": decided}


class UndoRequest(BaseModel):
    message_ids: list[str] | None = None
    cluster_label: str | None = None


@app.post("/api/undo")
async def undo(req: UndoRequest):
    """Remove decisions for individual messages or a cluster.

    If cluster_label is provided, removes the cluster-level decision AND
    all individual decisions for emails in that cluster.
    """
    session = _get_session()
    undone = 0

    if req.cluster_label:
        if req.cluster_label in session.decisions:
            del session.decisions[req.cluster_label]
            undone += 1

        # Also clear individual decisions for all emails in this cluster
        for c in _classifications:
            if _cluster_key(c) == req.cluster_label:
                key = str(c.message_id)
                if key in session.individual_decisions:
                    del session.individual_decisions[key]
                    undone += 1

    if req.message_ids:
        for mid in req.message_ids:
            key = str(mid)
            if key in session.individual_decisions:
                del session.individual_decisions[key]
                undone += 1

    _save()
    return {"status": "ok", "undone": undone}


@app.post("/api/decide-remaining")
async def decide_remaining(req: DecideRemainingRequest):
    """Mark all undecided emails as keep."""
    session = _get_session()
    ts = int(time.time())
    decided = 0

    for c in _classifications:
        if _msg_index.get(c.message_id) is None:
            continue
        dec = _resolve_decision(c, session)
        if dec is None:
            session.individual_decisions[str(c.message_id)] = {
                "action": "skip",
                "timestamp": ts,
            }
            decided += 1

    _save()
    return {"status": "ok", "decided": decided}


@app.post("/api/decide-cluster")
async def decide_cluster(req: DecideClusterRequest):
    """Record a cluster-level decision."""
    session = _get_session()
    action_map = {"reject": "skip"}
    internal = action_map.get(req.action, req.action)

    session.decisions[req.cluster_label] = {
        "action": internal,
        "timestamp": int(time.time()),
    }
    _save()
    return {"status": "ok", "cluster": req.cluster_label, "action": internal}


@app.get("/api/senders")
async def get_senders(
    group_by: str = Query("domain"),
    sort_by: str = Query("count"),
    sort_dir: str = Query("desc"),
    decision: str | None = Query(None),
    q: str | None = Query(None),
    tier: str | None = Query(None),
    confidence_min: float | None = Query(None),
    confidence_max: float | None = Query(None),
):
    """Aggregate emails by sender address or domain."""
    session = _get_session()
    groups: dict[str, list[tuple[Message, Classification]]] = defaultdict(list)

    for c in _classifications:
        msg = _msg_index.get(c.message_id)
        if msg is None:
            continue
        if tier and c.tier.value != tier:
            continue
        if confidence_min is not None and c.confidence < confidence_min:
            continue
        if confidence_max is not None and c.confidence > confidence_max:
            continue
        if q:
            q_lower = q.lower()
            if q_lower not in msg.subject.lower() and q_lower not in msg.sender_address.lower():
                continue

        key = msg.sender_address.lower() if group_by == "sender" else (
            msg.sender_address.split("@")[1].lower() if "@" in msg.sender_address else msg.sender_address.lower()
        )
        groups[key].append((msg, c))

    result = []
    for key, items in groups.items():
        trash_count = keep_count = pending_count = 0
        confs = []
        cluster_set: set[str] = set()
        tiers: dict[str, int] = defaultdict(int)

        for msg, c in items:
            dec = _resolve_decision(c, session)
            if dec == "approve":
                trash_count += 1
            elif dec == "skip":
                keep_count += 1
            else:
                pending_count += 1
            confs.append(c.confidence)
            cluster_set.add(_cluster_key(c))
            tiers[c.tier.value] += 1

        if decision:
            if decision == "pending" and pending_count == 0:
                continue
            elif decision == "approve" and trash_count == 0:
                continue
            elif decision == "skip" and keep_count == 0:
                continue

        result.append({
            "key": key,
            "count": len(items),
            "trash_count": trash_count,
            "keep_count": keep_count,
            "pending_count": pending_count,
            "avg_confidence": round(mean(confs), 4) if confs else 0,
            "top_clusters": sorted(cluster_set)[:5],
            "tiers": dict(tiers),
        })

    sort_field = sort_by if sort_by in ("key", "count", "avg_confidence", "trash_count", "keep_count", "pending_count") else "count"
    reverse = sort_dir != "asc"
    result.sort(key=lambda x: x[sort_field], reverse=reverse)

    return {"senders": result, "total": len(result), "group_by": group_by}


@app.get("/api/session")
async def get_session_state():
    """Current session state + progress stats."""
    session = _get_session()

    # Cluster progress
    all_clusters: set[str] = set()
    for c in _classifications:
        all_clusters.add(_cluster_key(c))
    decided_clusters = set(session.decisions.keys())
    reviewed = len(decided_clusters & all_clusters)

    # Email-level decisions
    individual_count = len(session.individual_decisions)
    approve_count = sum(
        1 for d in session.individual_decisions.values() if d.get("action") == "approve"
    )
    skip_count = sum(
        1 for d in session.individual_decisions.values() if d.get("action") == "skip"
    )

    # Cluster-level decisions
    cluster_approve = sum(
        1 for d in session.decisions.values() if d.get("action") == "approve"
    )
    cluster_skip = sum(
        1 for d in session.decisions.values() if d.get("action") == "skip"
    )

    # Effective counts: resolve each classification to its final decision
    effective_trash = 0
    effective_keep = 0
    for c in _classifications:
        dec = _resolve_decision(c, session)
        if dec == "approve":
            effective_trash += 1
        elif dec == "skip":
            effective_keep += 1
    effective_decided = effective_trash + effective_keep

    return {
        "session_id": session.session_id,
        "total_clusters": len(all_clusters),
        "reviewed_clusters": reviewed,
        "total_emails": len(_classifications),
        "individual_decisions": individual_count,
        "individual_trash": approve_count,
        "individual_keep": skip_count,
        "cluster_approve": cluster_approve,
        "cluster_skip": cluster_skip,
        "effective_decided": effective_decided,
        "effective_trash": effective_trash,
        "effective_keep": effective_keep,
        "auto_triage_summary": session.auto_triage_summary,
    }


@app.post("/api/auto-triage")
async def run_auto_triage():
    """Run auto_triage() and return results."""
    from icloud_cleanup.auto_triage import auto_triage

    result = auto_triage(_classifications, _sender_lookup)

    session = _get_session()
    session.auto_triage_summary = {
        "auto_resolved_count": result.auto_resolved_count,
        "auto_resolved_cluster_count": result.auto_resolved_cluster_count,
        "remaining_count": result.remaining_count,
        "remaining_cluster_count": result.remaining_cluster_count,
    }
    _save()

    return {
        "auto_resolved_count": result.auto_resolved_count,
        "auto_resolved_cluster_count": result.auto_resolved_cluster_count,
        "remaining_count": result.remaining_count,
        "remaining_cluster_count": result.remaining_cluster_count,
        "resolutions": [
            {
                "reason": r.reason,
                "count": len(r.message_ids),
                "tier": r.tier.value,
                "avg_confidence": round(r.avg_confidence, 3),
            }
            for r in result.auto_resolved
        ],
    }


@app.get("/api/protected-conflicts")
async def get_protected_conflicts():
    """Return approved-but-protected messages not yet overridden, grouped by sender."""
    session = _get_session()
    conflicts: dict[str, list[dict]] = defaultdict(list)

    for c in _classifications:
        if not c.protected:
            continue
        msg = _msg_index.get(c.message_id)
        if msg is None:
            continue

        dec = _resolve_decision(c, session)
        if dec != "approve":
            continue

        mid = str(c.message_id)
        if mid in session.protection_overrides:
            continue

        conflicts[msg.sender_address].append({
            "message_id": mid,
            "sender": msg.sender_address,
            "subject": msg.subject,
            "date": msg.date_received,
            "tier": c.tier.value,
            "confidence": round(c.confidence, 4),
            "signals": c.signals,
            "overridden": False,
        })

    # Also include already-overridden for UI state tracking
    overridden: dict[str, list[dict]] = defaultdict(list)
    for c in _classifications:
        if not c.protected:
            continue
        msg = _msg_index.get(c.message_id)
        if msg is None:
            continue
        mid = str(c.message_id)
        if mid not in session.protection_overrides:
            continue
        overridden[msg.sender_address].append({
            "message_id": mid,
            "sender": msg.sender_address,
            "subject": msg.subject,
            "date": msg.date_received,
            "tier": c.tier.value,
            "confidence": round(c.confidence, 4),
            "signals": c.signals,
            "overridden": True,
        })

    groups = []
    all_senders = set(conflicts.keys()) | set(overridden.keys())
    for sender in sorted(all_senders, key=lambda s: len(conflicts.get(s, [])), reverse=True):
        items = conflicts.get(sender, []) + overridden.get(sender, [])
        groups.append({
            "sender": sender,
            "pending_count": len(conflicts.get(sender, [])),
            "overridden_count": len(overridden.get(sender, [])),
            "emails": items,
        })

    total_pending = sum(len(v) for v in conflicts.values())
    total_overridden = sum(len(v) for v in overridden.values())

    return {
        "groups": groups,
        "total_pending": total_pending,
        "total_overridden": total_overridden,
    }


@app.post("/api/override-protection")
async def override_protection(req: OverrideProtectionRequest):
    """Add or remove message IDs from the protection override set."""
    session = _get_session()
    changed = 0

    for mid in req.message_ids:
        mid_str = str(mid)
        if req.override:
            if mid_str not in session.protection_overrides:
                session.protection_overrides.add(mid_str)
                changed += 1
        else:
            if mid_str in session.protection_overrides:
                session.protection_overrides.discard(mid_str)
                changed += 1

    _save()
    return {"status": "ok", "changed": changed, "override": req.override}


# --- Static files (must be last to avoid catching API routes) ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Launch ---

def launch(
    checkpoint_path: Path,
    session_path: Path,
    db_path: Path | None = None,
) -> None:
    """Load data and start the web review server."""
    import uvicorn

    from icloud_cleanup.scanner import (
        ENVELOPE_INDEX,
        ICLOUD_UUID,
        load_summaries,
        open_db,
        scan_messages,
    )

    global _checkpoint, _classifications, _messages, _msg_index
    global _sender_lookup, _session, _session_path, _db_path, _emlx_lookup, _summaries
    global _executed_ids

    # Load checkpoint
    _checkpoint = load_checkpoint(checkpoint_path)
    if not _checkpoint:
        raise SystemExit("No checkpoint found. Run 'classify' first.")
    _classifications = list(_checkpoint.values())

    # Load messages + summaries from DB
    effective_db = db_path or ENVELOPE_INDEX
    conn = open_db(effective_db)
    try:
        _messages = scan_messages(conn)
        _summaries = load_summaries(conn)
    finally:
        conn.close()

    _msg_index = {m.message_id: m for m in _messages}
    _sender_lookup = {m.message_id: m.sender_address for m in _messages}
    _db_path = effective_db
    _session_path = session_path

    # Load existing session if any
    existing = load_session(session_path)
    if existing:
        _session = existing
        print(f"  Resumed session {existing.session_id} ({len(existing.decisions)} cluster decisions)")

    # Load executed message IDs from action log
    action_log_path = Path.home() / ".icloud-cleanup" / "action_log.db"
    if action_log_path.exists():
        import sqlite3
        try:
            aconn = sqlite3.connect(action_log_path)
            rows = aconn.execute(
                "SELECT DISTINCT message_id FROM action_log "
                "WHERE action = 'move_to_trash' AND success = 1 AND dry_run = 0"
            ).fetchall()
            _executed_ids = {r[0] for r in rows}
            aconn.close()
            if _executed_ids:
                print(f"  {len(_executed_ids):,} previously executed deletions found")
        except Exception as exc:
            print(f"  Warning: Could not load action log: {exc}")

    # Build emlx lookup for body snippets
    try:
        from icloud_cleanup.emlx_parser import build_emlx_lookup

        mail_dir = Path.home() / "Library/Mail/V10"
        _emlx_lookup = build_emlx_lookup(mail_dir, ICLOUD_UUID)
    except Exception as exc:
        print(f"  Warning: Could not build emlx lookup: {exc}")
        _emlx_lookup = {}

    print(f"\n  iCloud Mail Cleanup — Web Review")
    print(f"  {len(_classifications):,} emails | {len(_emlx_lookup):,} .emlx bodies | {len(_summaries):,} summaries")
    print(f"  http://127.0.0.1:7842\n")

    webbrowser.open("http://127.0.0.1:7842")
    uvicorn.run(app, host="127.0.0.1", port=7842, log_level="warning")
