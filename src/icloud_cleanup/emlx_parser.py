"""EMLX file discovery and body text extraction.

Parses Apple Mail's .emlx format (byte-count + RFC 822 message + plist)
to extract plain-text body content for embedding and classification.
"""

from __future__ import annotations

import email
import html.parser
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)


class _HTMLStripper(html.parser.HTMLParser):
    """Stdlib-only HTML tag stripper that skips script/style content."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        return re.sub(r"\s+", " ", raw).strip()


def strip_html(html_text: str) -> str:
    """Remove HTML tags and collapse whitespace using stdlib only.

    Skips content inside <script> and <style> tags. Falls back to
    crude regex stripping if HTMLParser raises on malformed HTML.
    """
    stripper = _HTMLStripper()
    try:
        stripper.feed(html_text)
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text)).strip()
    return stripper.get_text()


def build_emlx_lookup(mail_dir: Path, account_uuid: str) -> dict[int, Path]:
    """Walk directory tree under account, return {ROWID: Path} for .emlx files.

    Skips .partial.emlx files (headers-only, no body content) and
    files with non-numeric stems. Default mail_dir is ~/Library/Mail/V10.
    """
    lookup: dict[int, Path] = {}
    account_dir = mail_dir / account_uuid
    if not account_dir.exists():
        return lookup
    for emlx_path in account_dir.rglob("*.emlx"):
        stem = emlx_path.stem
        if ".partial" in stem:
            continue
        try:
            rowid = int(stem)
            lookup[rowid] = emlx_path
        except ValueError:
            continue
    return lookup


def parse_emlx_body(path: Path, max_chars: int = 4000) -> str | None:
    """Extract plain text body from .emlx file.

    Returns None if file is missing, corrupt, or has no text content.
    Truncates to max_chars to align with embedding model context window.
    """
    try:
        with open(path, "rb") as f:
            bytecount = int(f.readline().strip())
            msg_bytes = f.read(bytecount)
        msg = email.message_from_bytes(msg_bytes)
    except Exception as exc:
        log.warning("Failed to parse %s: %s", path.name, exc)
        return None

    # Non-multipart message
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if not payload:
            return None
        ct = msg.get_content_type()
        if ct not in ("text/plain", "text/html"):
            return None
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if ct == "text/html":
            text = strip_html(text)
        return text[:max_chars] if text.strip() else None

    # Multipart: prefer text/plain
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if text.strip():
                    return text[:max_chars]

    # Fallback: text/html with tag stripping
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                html_text = payload.decode(charset, errors="replace")
                text = strip_html(html_text)
                if text.strip():
                    return text[:max_chars]

    return None
