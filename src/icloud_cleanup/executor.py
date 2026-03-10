"""Safe execution engine: AppleScript generation, action log, batch execution."""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

from icloud_cleanup.models import Classification, Message

log = logging.getLogger(__name__)

ICLOUD_ACCOUNT = "iCloud"
TRASH_MAILBOX = "Deleted Messages"


def url_to_applescript_mailbox(mailbox_url: str) -> str:
    """Convert Envelope Index mailbox URL to AppleScript mailbox reference.

    Strips imap://UUID/ prefix and URL-decodes the path.
    """
    # URL format: imap://UUID/path or imap://UUID/path/subpath
    parts = mailbox_url.split("/", 3)
    path = unquote(parts[3]) if len(parts) > 3 else ""
    return f'mailbox "{path}" of account "{ICLOUD_ACCOUNT}"'


def generate_applescript(
    rowid: int,
    source_mailbox: str,
    trash_mailbox: str = TRASH_MAILBOX,
) -> str:
    """Build AppleScript to move a single message by ROWID to trash."""
    return f'''tell application "Mail"
    set targetMailbox to {source_mailbox}
    set trashMailbox to mailbox "{trash_mailbox}" of account "{ICLOUD_ACCOUNT}"
    set matchedMsgs to (every message of targetMailbox whose id is {rowid})
    if (count of matchedMsgs) > 0 then
        set mailbox of item 1 of matchedMsgs to trashMailbox
    end if
end tell'''


def generate_restore_script(
    rowid: int,
    original_mailbox: str,
) -> str:
    """Build AppleScript to restore a single message from trash."""
    return f'''tell application "Mail"
    set trashMailbox to mailbox "{TRASH_MAILBOX}" of account "{ICLOUD_ACCOUNT}"
    set originalMailbox to {original_mailbox}
    set matchedMsgs to (every message of trashMailbox whose id is {rowid})
    if (count of matchedMsgs) > 0 then
        set mailbox of item 1 of matchedMsgs to originalMailbox
    end if
end tell'''


# --- Batch AppleScript generation ---


def generate_batch_applescript(
    batch: list[Message],
    classifications: dict[int, Classification],
    trash_mailbox: str = TRASH_MAILBOX,
) -> tuple[str, list[int]]:
    """Build a single AppleScript that moves all messages in batch to trash.

    Groups messages by source mailbox for efficiency. Each message gets its own
    try/on error block for individual error tracking. Returns (script, rowids)
    where rowids is the ordered list of ROWIDs included in the script.
    """
    # Group by AppleScript mailbox reference
    by_mailbox: dict[str, list[int]] = defaultdict(list)
    rowid_order: list[int] = []
    for msg in batch:
        cls = classifications.get(msg.message_id)
        if cls is None or cls.protected:
            continue
        ref = url_to_applescript_mailbox(msg.mailbox_url)
        by_mailbox[ref].append(msg.rowid)
        rowid_order.append(msg.rowid)

    if not rowid_order:
        return "", []

    lines = [
        'tell application "Mail"',
        f'    set trashMailbox to mailbox "{trash_mailbox}" of account "{ICLOUD_ACCOUNT}"',
        '    set results to ""',
    ]
    for mailbox_ref, rowids in by_mailbox.items():
        lines.append(f"    set mb to {mailbox_ref}")
        for rid in rowids:
            lines.extend([
                "    try",
                f"        set matched to (every message of mb whose id is {rid})",
                "        if (count of matched) > 0 then",
                "            set mailbox of item 1 of matched to trashMailbox",
                f'            set results to results & "OK:{rid}" & linefeed',
                "        else",
                f'            set results to results & "MISS:{rid}" & linefeed',
                "        end if",
                "    on error errMsg",
                f'        set results to results & "ERR:{rid}:" & errMsg & linefeed',
                "    end try",
            ])
    lines.append("    return results")
    lines.append("end tell")

    return "\n".join(lines), rowid_order


def generate_batch_restore_script(
    entries: list[dict],
) -> tuple[str, list[int]]:
    """Build a single AppleScript that restores all entries from trash.

    Returns (script, rowids) where rowids is the ordered list of ROWIDs.
    """
    if not entries:
        return "", []

    by_mailbox: dict[str, list[int]] = defaultdict(list)
    rowid_order: list[int] = []
    for entry in entries:
        source_mailbox = entry["source_mailbox"]
        if source_mailbox and source_mailbox.startswith("imap://"):
            ref = url_to_applescript_mailbox(source_mailbox)
        else:
            ref = f'mailbox "{source_mailbox}" of account "{ICLOUD_ACCOUNT}"'
        by_mailbox[ref].append(entry["rowid_in_db"])
        rowid_order.append(entry["rowid_in_db"])

    lines = [
        'tell application "Mail"',
        f'    set trashMailbox to mailbox "{TRASH_MAILBOX}" of account "{ICLOUD_ACCOUNT}"',
        '    set results to ""',
    ]
    for mailbox_ref, rowids in by_mailbox.items():
        lines.append(f"    set mb to {mailbox_ref}")
        for rid in rowids:
            lines.extend([
                "    try",
                f"        set matched to (every message of trashMailbox whose id is {rid})",
                "        if (count of matched) > 0 then",
                "            set mailbox of item 1 of matched to mb",
                f'            set results to results & "OK:{rid}" & linefeed',
                "        else",
                f'            set results to results & "MISS:{rid}" & linefeed',
                "        end if",
                "    on error errMsg",
                f'        set results to results & "ERR:{rid}:" & errMsg & linefeed',
                "    end try",
            ])
    lines.append("    return results")
    lines.append("end tell")

    return "\n".join(lines), rowid_order


def _parse_batch_results(stdout: str) -> dict[int, tuple[str, str | None]]:
    """Parse batch AppleScript output into per-ROWID results.

    Returns dict mapping rowid -> (status, error_msg_or_None).
    Status is "OK", "MISS", or "ERR".
    """
    results: dict[int, tuple[str, str | None]] = {}
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("OK:"):
            rid = int(line[3:])
            results[rid] = ("OK", None)
        elif line.startswith("MISS:"):
            rid = int(line[5:])
            results[rid] = ("MISS", None)
        elif line.startswith("ERR:"):
            # ERR:rowid:error message
            rest = line[4:]
            colon_idx = rest.index(":")
            rid = int(rest[:colon_idx])
            err_msg = rest[colon_idx + 1:]
            results[rid] = ("ERR", err_msg)
    return results


class ActionLog:
    """SQLite-backed audit trail for all execution actions."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                rowid_in_db INTEGER NOT NULL,
                subject TEXT,
                sender_address TEXT,
                tier TEXT NOT NULL,
                confidence REAL,
                action TEXT NOT NULL,
                source_mailbox TEXT,
                timestamp INTEGER NOT NULL,
                dry_run BOOLEAN NOT NULL DEFAULT 1,
                success BOOLEAN,
                error_message TEXT,
                reversible BOOLEAN NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_action_log_message_id
                ON action_log(message_id);
            CREATE INDEX IF NOT EXISTS idx_action_log_timestamp
                ON action_log(timestamp);
        """)

    def _insert_action(
        self,
        *,
        message_id: int,
        rowid_in_db: int,
        subject: str | None,
        sender_address: str | None,
        tier: str,
        confidence: float,
        action: str,
        source_mailbox: str | None,
        dry_run: bool,
        success: bool,
        error_message: str | None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO action_log
            (message_id, rowid_in_db, subject, sender_address, tier, confidence,
             action, source_mailbox, timestamp, dry_run, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                message_id, rowid_in_db, subject, sender_address, tier,
                confidence, action, source_mailbox, int(time.time()),
                dry_run, success, error_message,
            ),
        )

    def log_action(
        self,
        *,
        message_id: int,
        rowid_in_db: int,
        subject: str | None,
        sender_address: str | None,
        tier: str,
        confidence: float,
        action: str,
        source_mailbox: str | None,
        dry_run: bool,
        success: bool,
        error_message: str | None,
    ) -> None:
        self._insert_action(
            message_id=message_id, rowid_in_db=rowid_in_db, subject=subject,
            sender_address=sender_address, tier=tier, confidence=confidence,
            action=action, source_mailbox=source_mailbox, dry_run=dry_run,
            success=success, error_message=error_message,
        )
        self._conn.commit()

    def log_action_no_commit(
        self,
        *,
        message_id: int,
        rowid_in_db: int,
        subject: str | None,
        sender_address: str | None,
        tier: str,
        confidence: float,
        action: str,
        source_mailbox: str | None,
        dry_run: bool,
        success: bool,
        error_message: str | None,
    ) -> None:
        """Insert action without committing — call commit() after the batch."""
        self._insert_action(
            message_id=message_id, rowid_in_db=rowid_in_db, subject=subject,
            sender_address=sender_address, tier=tier, confidence=confidence,
            action=action, source_mailbox=source_mailbox, dry_run=dry_run,
            success=success, error_message=error_message,
        )

    def commit(self) -> None:
        self._conn.commit()

    def get_actions(
        self,
        action: str | None = None,
        dry_run: bool | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query = "SELECT * FROM action_log WHERE 1=1"
        params: list = []
        if action is not None:
            query += " AND action = ?"
            params.append(action)
        if dry_run is not None:
            query += " AND dry_run = ?"
            params.append(dry_run)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_restorable(self) -> list[dict]:
        """Actions that can be reversed: real successful trash moves."""
        rows = self._conn.execute(
            """SELECT * FROM action_log
            WHERE action = 'move_to_trash' AND success = 1 AND dry_run = 0
            ORDER BY timestamp DESC""",
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._conn.close()


def execute_deletions(
    messages: list[Message],
    classifications: dict[int, Classification],
    action_log: ActionLog,
    dry_run: bool = True,
    batch_size: int = 100,
    batch_pause: float = 2.0,
) -> dict:
    """Execute approved deletions via batched AppleScript with audit logging.

    Each batch of messages is handled by a single osascript process instead of
    one per message. Returns summary dict with success_count, error_count,
    skipped_protected, errors.
    """
    success_count = 0
    error_count = 0
    skipped_protected = 0
    errors: list[str] = []

    # Build rowid -> msg lookup for logging after batch execution
    rowid_to_msg: dict[int, Message] = {m.rowid: m for m in messages}

    for batch_start in range(0, len(messages), batch_size):
        batch = messages[batch_start : batch_start + batch_size]

        # Log protected messages first (these are excluded from the script)
        for msg in batch:
            cls = classifications.get(msg.message_id)
            if cls is None:
                continue
            if cls.protected:
                skipped_protected += 1
                action_log.log_action_no_commit(
                    message_id=msg.message_id,
                    rowid_in_db=msg.rowid,
                    subject=msg.subject,
                    sender_address=msg.sender_address,
                    tier=cls.tier.value,
                    confidence=cls.confidence,
                    action="skip_protected",
                    source_mailbox=msg.mailbox_url,
                    dry_run=dry_run,
                    success=False,
                    error_message="Protected message rejected from execution",
                )
                log.warning(
                    "Protected message rejected: rowid=%d subject=%s",
                    msg.rowid, msg.subject,
                )

        script, rowids = generate_batch_applescript(batch, classifications)

        if not rowids:
            action_log.commit()
            continue

        if dry_run:
            for rid in rowids:
                msg = rowid_to_msg[rid]
                cls = classifications[msg.message_id]
                action_log.log_action_no_commit(
                    message_id=msg.message_id,
                    rowid_in_db=msg.rowid,
                    subject=msg.subject,
                    sender_address=msg.sender_address,
                    tier=cls.tier.value,
                    confidence=cls.confidence,
                    action="move_to_trash",
                    source_mailbox=msg.mailbox_url,
                    dry_run=True,
                    success=True,
                    error_message=None,
                )
                success_count += 1
        else:
            # Single osascript call for entire batch
            timeout = max(30, len(rowids) * 2)
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0 and not result.stdout.strip():
                # Whole batch failed
                err_msg = result.stderr.strip()
                for rid in rowids:
                    msg = rowid_to_msg[rid]
                    cls = classifications[msg.message_id]
                    action_log.log_action_no_commit(
                        message_id=msg.message_id,
                        rowid_in_db=msg.rowid,
                        subject=msg.subject,
                        sender_address=msg.sender_address,
                        tier=cls.tier.value,
                        confidence=cls.confidence,
                        action="move_to_trash",
                        source_mailbox=msg.mailbox_url,
                        dry_run=False,
                        success=False,
                        error_message=err_msg,
                    )
                    error_count += 1
                    errors.append(f"ROWID {rid}: {err_msg}")
            else:
                parsed = _parse_batch_results(result.stdout)
                for rid in rowids:
                    msg = rowid_to_msg[rid]
                    cls = classifications[msg.message_id]
                    status, err_msg = parsed.get(rid, ("ERR", "No result from osascript"))
                    ok = status == "OK"
                    action_log.log_action_no_commit(
                        message_id=msg.message_id,
                        rowid_in_db=msg.rowid,
                        subject=msg.subject,
                        sender_address=msg.sender_address,
                        tier=cls.tier.value,
                        confidence=cls.confidence,
                        action="move_to_trash",
                        source_mailbox=msg.mailbox_url,
                        dry_run=False,
                        success=ok,
                        error_message=err_msg,
                    )
                    if ok:
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append(f"ROWID {rid}: {err_msg}")

        action_log.commit()

        # Pause between batches (not after last batch)
        if batch_start + batch_size < len(messages):
            time.sleep(batch_pause)

    return {
        "success_count": success_count,
        "error_count": error_count,
        "skipped_protected": skipped_protected,
        "errors": errors,
    }


def restore_from_log(
    action_log: ActionLog,
    dry_run: bool = True,
    batch_size: int = 100,
    batch_pause: float = 2.0,
) -> dict:
    """Restore previously trashed messages from the action log using batched AppleScript."""
    restorable = action_log.get_restorable()
    success_count = 0
    error_count = 0
    errors: list[str] = []

    # Build rowid -> entry lookup
    rowid_to_entry: dict[int, dict] = {e["rowid_in_db"]: e for e in restorable}

    for batch_start in range(0, len(restorable), batch_size):
        batch = restorable[batch_start : batch_start + batch_size]

        script, rowids = generate_batch_restore_script(batch)

        if not rowids:
            continue

        if dry_run:
            for rid in rowids:
                entry = rowid_to_entry[rid]
                action_log.log_action_no_commit(
                    message_id=entry["message_id"],
                    rowid_in_db=entry["rowid_in_db"],
                    subject=entry.get("subject"),
                    sender_address=entry.get("sender_address"),
                    tier=entry["tier"],
                    confidence=entry.get("confidence", 0.0),
                    action="restore",
                    source_mailbox=entry["source_mailbox"],
                    dry_run=True,
                    success=True,
                    error_message=None,
                )
                success_count += 1
        else:
            timeout = max(30, len(rowids) * 2)
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0 and not result.stdout.strip():
                err_msg = result.stderr.strip()
                for rid in rowids:
                    entry = rowid_to_entry[rid]
                    action_log.log_action_no_commit(
                        message_id=entry["message_id"],
                        rowid_in_db=entry["rowid_in_db"],
                        subject=entry.get("subject"),
                        sender_address=entry.get("sender_address"),
                        tier=entry["tier"],
                        confidence=entry.get("confidence", 0.0),
                        action="restore",
                        source_mailbox=entry["source_mailbox"],
                        dry_run=False,
                        success=False,
                        error_message=err_msg,
                    )
                    error_count += 1
                    errors.append(f"ROWID {rid}: {err_msg}")
            else:
                parsed = _parse_batch_results(result.stdout)
                for rid in rowids:
                    entry = rowid_to_entry[rid]
                    status, err_msg = parsed.get(rid, ("ERR", "No result from osascript"))
                    ok = status == "OK"
                    action_log.log_action_no_commit(
                        message_id=entry["message_id"],
                        rowid_in_db=entry["rowid_in_db"],
                        subject=entry.get("subject"),
                        sender_address=entry.get("sender_address"),
                        tier=entry["tier"],
                        confidence=entry.get("confidence", 0.0),
                        action="restore",
                        source_mailbox=entry["source_mailbox"],
                        dry_run=False,
                        success=ok,
                        error_message=err_msg,
                    )
                    if ok:
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append(f"ROWID {rid}: {err_msg}")

        action_log.commit()

        if batch_start + batch_size < len(restorable):
            time.sleep(batch_pause)

    return {
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors,
    }
