"""Safe execution engine: AppleScript generation, action log, batch execution."""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import time
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
    """Build AppleScript to move a message by ROWID to trash.

    source_mailbox should be an AppleScript reference string
    (output of url_to_applescript_mailbox).
    """
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
    """Build AppleScript to restore a message from Deleted Messages to its original mailbox."""
    return f'''tell application "Mail"
    set trashMailbox to mailbox "{TRASH_MAILBOX}" of account "{ICLOUD_ACCOUNT}"
    set originalMailbox to {original_mailbox}
    set matchedMsgs to (every message of trashMailbox whose id is {rowid})
    if (count of matchedMsgs) > 0 then
        set mailbox of item 1 of matchedMsgs to originalMailbox
    end if
end tell'''


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
    """Execute approved deletions via AppleScript with audit logging.

    Returns summary dict with success_count, error_count, skipped_protected, errors.
    """
    success_count = 0
    error_count = 0
    skipped_protected = 0
    errors: list[str] = []

    for batch_start in range(0, len(messages), batch_size):
        batch = messages[batch_start : batch_start + batch_size]

        for msg in batch:
            cls = classifications.get(msg.message_id)
            if cls is None:
                continue

            # Safety: reject protected messages
            if cls.protected:
                skipped_protected += 1
                action_log.log_action(
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
                continue

            source_ref = url_to_applescript_mailbox(msg.mailbox_url)
            script = generate_applescript(msg.rowid, source_ref)

            if dry_run:
                action_log.log_action(
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
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                ok = result.returncode == 0
                err_msg = result.stderr.strip() if not ok else None
                action_log.log_action(
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
                    errors.append(f"ROWID {msg.rowid}: {err_msg}")

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
    """Restore previously trashed messages from the action log."""
    restorable = action_log.get_restorable()
    success_count = 0
    error_count = 0
    errors: list[str] = []

    for batch_start in range(0, len(restorable), batch_size):
        batch = restorable[batch_start : batch_start + batch_size]

        for entry in batch:
            source_mailbox = entry["source_mailbox"]
            # If the source looks like a URL, convert it; otherwise use as-is
            if source_mailbox and source_mailbox.startswith("imap://"):
                original_ref = url_to_applescript_mailbox(source_mailbox)
            else:
                original_ref = f'mailbox "{source_mailbox}" of account "{ICLOUD_ACCOUNT}"'

            script = generate_restore_script(entry["rowid_in_db"], original_ref)

            if dry_run:
                action_log.log_action(
                    message_id=entry["message_id"],
                    rowid_in_db=entry["rowid_in_db"],
                    subject=entry.get("subject"),
                    sender_address=entry.get("sender_address"),
                    tier=entry["tier"],
                    confidence=entry.get("confidence", 0.0),
                    action="restore",
                    source_mailbox=source_mailbox,
                    dry_run=True,
                    success=True,
                    error_message=None,
                )
                success_count += 1
            else:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                ok = result.returncode == 0
                err_msg = result.stderr.strip() if not ok else None
                action_log.log_action(
                    message_id=entry["message_id"],
                    rowid_in_db=entry["rowid_in_db"],
                    subject=entry.get("subject"),
                    sender_address=entry.get("sender_address"),
                    tier=entry["tier"],
                    confidence=entry.get("confidence", 0.0),
                    action="restore",
                    source_mailbox=source_mailbox,
                    dry_run=False,
                    success=ok,
                    error_message=err_msg,
                )
                if ok:
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"ROWID {entry['rowid_in_db']}: {err_msg}")

        if batch_start + batch_size < len(restorable):
            time.sleep(batch_pause)

    return {
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors,
    }
