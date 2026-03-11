"""Database access layer for reading the Envelope Index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from icloud_cleanup.models import Message

ENVELOPE_INDEX = Path.home() / "Library/Mail/V10/MailData/Envelope Index"
ICLOUD_UUID: str | None = None  # auto-detected on first DB open


def _detect_icloud_uuid(conn: sqlite3.Connection) -> str:
    """Auto-detect iCloud account UUID from mailboxes table."""
    row = conn.execute(
        "SELECT url FROM mailboxes WHERE url LIKE 'imap://%/INBOX' LIMIT 1"
    ).fetchone()
    if row:
        # url format: imap://UUID/INBOX
        url = row[0] if isinstance(row, (tuple, list)) else row["url"]
        parts = url.split("/")
        if len(parts) >= 3:
            return parts[2]
    raise RuntimeError(
        "Could not auto-detect iCloud UUID from mailboxes table. "
        "Set ICLOUD_MAIL_UUID environment variable."
    )


def open_db(path: Path | None = None) -> sqlite3.Connection:
    """Open the Envelope Index in URI read-only mode.

    Uses the default system path if none provided.
    Auto-detects ICLOUD_UUID on first call.
    """
    global ICLOUD_UUID
    target = path or ENVELOPE_INDEX
    uri = f"file:{target}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    if ICLOUD_UUID is None:
        import os
        env_uuid = os.environ.get("ICLOUD_MAIL_UUID")
        if env_uuid:
            ICLOUD_UUID = env_uuid
        else:
            ICLOUD_UUID = _detect_icloud_uuid(conn)
    return conn


def scan_messages(conn: sqlite3.Connection) -> list[Message]:
    """Bulk-extract all iCloud messages as typed Message objects."""
    # Detect if server_messages table exists (absent in older Mail versions)
    has_server_messages = False
    try:
        conn.execute("SELECT 1 FROM server_messages LIMIT 1")
        has_server_messages = True
    except sqlite3.OperationalError:
        pass

    sm_join = "LEFT JOIN server_messages sm ON sm.message = m.ROWID" if has_server_messages else ""
    sm_select = "COALESCE(sm.junk_level, 0) as junk_level," if has_server_messages else "0 as junk_level,"

    query = f"""
    SELECT
        m.ROWID as rowid,
        m.message_id,
        m.conversation_id,
        m.flags,
        m.read,
        m.flagged,
        m.deleted,
        m.size,
        m.date_received,
        m.list_id_hash,
        m.unsubscribe_type,
        m.automated_conversation,
        COALESCE(a.address, '') as sender_address,
        COALESCE(s.subject, '') as subject,
        mb.url as mailbox_url,
        mgd.model_category,
        mgd.model_high_impact,
        {sm_select}
        COALESCE(mgd.urgent, 0) as urgent,
        mgd.model_subcategory
    FROM messages m
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    LEFT JOIN addresses a ON m.sender = a.ROWID
    LEFT JOIN subjects s ON m.subject = s.ROWID
    LEFT JOIN message_global_data mgd ON m.message_id = mgd.message_id
    {sm_join}
    WHERE mb.url LIKE ?
    ORDER BY m.date_received DESC
    """
    cursor = conn.execute(query, (f"imap://{ICLOUD_UUID}/%",))
    return [
        Message(
            rowid=row["rowid"],
            message_id=row["message_id"],
            conversation_id=row["conversation_id"],
            flags=row["flags"],
            read=row["read"],
            flagged=row["flagged"],
            deleted=row["deleted"],
            size=row["size"],
            date_received=row["date_received"],
            sender_address=row["sender_address"],
            subject=row["subject"],
            mailbox_url=row["mailbox_url"],
            list_id_hash=row["list_id_hash"],
            unsubscribe_type=row["unsubscribe_type"],
            automated_conversation=row["automated_conversation"],
            model_category=row["model_category"],
            model_high_impact=row["model_high_impact"],
            junk_level=row["junk_level"],
            urgent=row["urgent"],
            model_subcategory=row["model_subcategory"],
        )
        for row in cursor
    ]


def get_sender_stats(conn: sqlite3.Connection) -> dict[str, dict]:
    """Aggregate sender volume statistics from iCloud inbox mailboxes.

    Groups by lowercase address, excludes Sent/Drafts.
    Returns dict keyed by lowercase address with count, total_size, min_date, max_date.
    """
    query = """
    SELECT
        LOWER(a.address) as address,
        COUNT(*) as count,
        SUM(m.size) as total_size,
        MIN(m.date_received) as min_date,
        MAX(m.date_received) as max_date
    FROM messages m
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    LEFT JOIN addresses a ON m.sender = a.ROWID
    WHERE mb.url LIKE ?
      AND mb.url NOT LIKE '%/Sent%'
      AND mb.url NOT LIKE '%/Drafts%'
      AND a.address IS NOT NULL
    GROUP BY LOWER(a.address)
    """
    cursor = conn.execute(query, (f"imap://{ICLOUD_UUID}/%",))
    return {
        row["address"]: {
            "count": row["count"],
            "total_size": row["total_size"],
            "min_date": row["min_date"],
            "max_date": row["max_date"],
        }
        for row in cursor
    }


def get_sent_recipients(conn: sqlite3.Connection) -> dict[str, dict]:
    """Extract recipients from iCloud Sent mailbox.

    Returns dict keyed by lowercase address with times_sent_to and last_sent_to.
    """
    query = """
    SELECT
        LOWER(a.address) as address,
        COUNT(*) as times_sent_to,
        MAX(m.date_received) as last_sent_to
    FROM messages m
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    JOIN recipients r ON r.message = m.ROWID
    JOIN addresses a ON r.address = a.ROWID
    WHERE mb.url LIKE ?
    GROUP BY LOWER(a.address)
    """
    cursor = conn.execute(query, (f"imap://{ICLOUD_UUID}/Sent%",))
    return {
        row["address"]: {
            "times_sent_to": row["times_sent_to"],
            "last_sent_to": row["last_sent_to"],
        }
        for row in cursor
    }


def get_sender_display_names(conn: sqlite3.Connection) -> dict[str, str]:
    """Map lowercase sender address to display name from addresses.comment."""
    query = """
    SELECT LOWER(address) as addr, comment
    FROM addresses
    WHERE comment IS NOT NULL AND comment != ''
    """
    cursor = conn.execute(query)
    result: dict[str, str] = {}
    for row in cursor:
        addr = row["addr"]
        if addr and addr not in result:
            result[addr] = row["comment"]
    return result


def get_document_attachment_message_ids(conn: sqlite3.Connection) -> set[int]:
    """Return message ROWIDs that have document attachments.

    Covers PDF, DOC, XLS, ICS, and other document-type extensions.
    """
    doc_extensions = (
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv",
        ".ppt", ".pptx", ".ics", ".vcf", ".zip", ".rar",
    )
    query = """
    SELECT m.ROWID as msg_rowid, LOWER(a.name) as filename
    FROM messages m
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    JOIN attachments a ON a.message = m.ROWID
    WHERE mb.url LIKE ?
      AND a.name IS NOT NULL
    """
    cursor = conn.execute(query, (f"imap://{ICLOUD_UUID}/%",))
    result: set[int] = set()
    for row in cursor:
        filename = row["filename"]
        if filename and any(filename.endswith(ext) for ext in doc_extensions):
            result.add(row["msg_rowid"])
    return result


def load_summaries(conn: sqlite3.Connection) -> dict[int, str]:
    """Load email summaries from the Envelope Index summaries table.

    Returns {message_id: summary_text} for iCloud messages that have summaries.
    """
    query = """
    SELECT m.message_id, s.summary
    FROM messages m
    JOIN summaries s ON m.summary = s.ROWID
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    WHERE mb.url LIKE ?
      AND s.summary IS NOT NULL
      AND s.summary != ''
    """
    try:
        cursor = conn.execute(query, (f"imap://{ICLOUD_UUID}/%",))
        return {row["message_id"]: row["summary"] for row in cursor}
    except sqlite3.OperationalError:
        # summaries table may not exist in older Mail versions
        return {}


def get_replied_conversation_ids(conn: sqlite3.Connection) -> set[int]:
    """Get conversation IDs that have messages in the Sent mailbox.

    Excludes conversation_id = 0 (unthreaded messages).
    """
    query = """
    SELECT DISTINCT conversation_id
    FROM messages m
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    WHERE mb.url LIKE ?
      AND conversation_id > 0
    """
    cursor = conn.execute(query, (f"imap://{ICLOUD_UUID}/Sent%",))
    return {row["conversation_id"] for row in cursor}
