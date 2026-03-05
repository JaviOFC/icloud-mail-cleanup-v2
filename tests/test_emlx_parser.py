"""Tests for EMLX file parsing — lookup table, body extraction, HTML stripping."""

from __future__ import annotations

import email.mime.multipart
import email.mime.text
from pathlib import Path

import pytest

from icloud_cleanup.emlx_parser import build_emlx_lookup, parse_emlx_body, strip_html


def _make_emlx(path: Path, body: bytes, content_type: str = "text/plain", charset: str = "utf-8") -> None:
    """Create a minimal .emlx file with byte-count header + RFC822 message."""
    msg = email.mime.text.MIMEText(body.decode(charset, errors="replace"), content_type.split("/")[1], charset)
    msg["From"] = "test@example.com"
    msg["Subject"] = "Test"
    msg_bytes = msg.as_bytes()
    with open(path, "wb") as f:
        f.write(f"{len(msg_bytes)}\n".encode())
        f.write(msg_bytes)
        # Empty plist trailer (real .emlx files have this)
        f.write(b"\n<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<plist version=\"1.0\"><dict/></plist>\n")


def _make_multipart_emlx(path: Path, text_plain: str | None = None, text_html: str | None = None, charset: str = "utf-8") -> None:
    """Create a multipart .emlx file with optional text/plain and text/html parts."""
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["From"] = "test@example.com"
    msg["Subject"] = "Test Multipart"
    if text_plain is not None:
        msg.attach(email.mime.text.MIMEText(text_plain, "plain", charset))
    if text_html is not None:
        msg.attach(email.mime.text.MIMEText(text_html, "html", charset))
    msg_bytes = msg.as_bytes()
    with open(path, "wb") as f:
        f.write(f"{len(msg_bytes)}\n".encode())
        f.write(msg_bytes)
        f.write(b"\n<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<plist version=\"1.0\"><dict/></plist>\n")


class TestLookupTable:
    """Tests for build_emlx_lookup — ROWID-to-Path mapping."""

    def test_finds_emlx_files(self, tmp_path: Path):
        """Discovers .emlx files and maps ROWID (stem) to path."""
        account_dir = tmp_path / "ACCOUNT-UUID"
        messages_dir = account_dir / "INBOX.mbox" / "Messages"
        messages_dir.mkdir(parents=True)
        emlx = messages_dir / "39493.emlx"
        _make_emlx(emlx, b"Hello world")
        lookup = build_emlx_lookup(tmp_path, "ACCOUNT-UUID")
        assert 39493 in lookup
        assert lookup[39493] == emlx

    def test_skips_partial_emlx(self, tmp_path: Path):
        """Skips .partial.emlx files (headers only, no body)."""
        account_dir = tmp_path / "ACCOUNT-UUID"
        messages_dir = account_dir / "INBOX.mbox" / "Messages"
        messages_dir.mkdir(parents=True)
        (messages_dir / "100.emlx").touch()
        (messages_dir / "100.partial.emlx").touch()
        lookup = build_emlx_lookup(tmp_path, "ACCOUNT-UUID")
        assert 100 in lookup
        # The partial should not be in the lookup
        for path in lookup.values():
            assert ".partial" not in path.stem

    def test_ignores_non_numeric_filenames(self, tmp_path: Path):
        """Skips .emlx files with non-numeric stems gracefully."""
        account_dir = tmp_path / "ACCOUNT-UUID"
        messages_dir = account_dir / "INBOX.mbox" / "Messages"
        messages_dir.mkdir(parents=True)
        (messages_dir / "metadata.emlx").touch()
        (messages_dir / "draft-abc.emlx").touch()
        (messages_dir / "42.emlx").touch()
        lookup = build_emlx_lookup(tmp_path, "ACCOUNT-UUID")
        assert len(lookup) == 1
        assert 42 in lookup

    def test_multiple_mailboxes(self, tmp_path: Path):
        """Finds .emlx files across multiple mailbox subdirectories."""
        account_dir = tmp_path / "ACCOUNT-UUID"
        for mbox in ["INBOX.mbox", "Sent.mbox", "Archive.mbox"]:
            msgs = account_dir / mbox / "Messages"
            msgs.mkdir(parents=True)
            _make_emlx(msgs / f"{hash(mbox) % 10000}.emlx", b"body")
        lookup = build_emlx_lookup(tmp_path, "ACCOUNT-UUID")
        assert len(lookup) == 3

    def test_empty_directory(self, tmp_path: Path):
        """Returns empty dict when no .emlx files exist."""
        account_dir = tmp_path / "ACCOUNT-UUID"
        account_dir.mkdir()
        lookup = build_emlx_lookup(tmp_path, "ACCOUNT-UUID")
        assert lookup == {}


class TestHtmlStripping:
    """Tests for strip_html — stdlib-only HTML tag removal."""

    def test_removes_tags(self):
        assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self):
        result = strip_html("<p>Hello</p>   <p>World</p>")
        assert "  " not in result
        assert "Hello" in result
        assert "World" in result

    def test_skips_script_content(self):
        html = "<p>Keep</p><script>var x = 1;</script><p>this</p>"
        result = strip_html(html)
        assert "var x" not in result
        assert "Keep" in result
        assert "this" in result

    def test_skips_style_content(self):
        html = "<p>Keep</p><style>body{color:red}</style><p>this</p>"
        result = strip_html(html)
        assert "color:red" not in result
        assert "Keep" in result

    def test_handles_malformed_html_without_crashing(self):
        """Malformed HTML doesn't raise — falls back to regex strip."""
        result = strip_html("<p>Unclosed <b>tag <i>mess")
        assert isinstance(result, str)
        assert "Unclosed" in result

    def test_empty_string(self):
        assert strip_html("") == ""

    def test_plain_text_passthrough(self):
        assert strip_html("No tags here") == "No tags here"


class TestBodyExtraction:
    """Tests for parse_emlx_body — RFC822 body extraction from .emlx format."""

    def test_extracts_text_plain(self, tmp_path: Path):
        """Extracts text/plain body from a simple .emlx file."""
        emlx = tmp_path / "1.emlx"
        _make_emlx(emlx, b"Hello from the email body")
        result = parse_emlx_body(emlx)
        assert result is not None
        assert "Hello from the email body" in result

    def test_strips_html_for_html_only(self, tmp_path: Path):
        """Strips HTML tags for HTML-only emails."""
        emlx = tmp_path / "2.emlx"
        _make_emlx(emlx, b"<html><body><p>Hello <b>World</b></p></body></html>", "text/html")
        result = parse_emlx_body(emlx)
        assert result is not None
        assert "<p>" not in result
        assert "<b>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_multipart_prefers_text_plain(self, tmp_path: Path):
        """For multipart emails, prefers text/plain over text/html."""
        emlx = tmp_path / "3.emlx"
        _make_multipart_emlx(emlx, text_plain="Plain version", text_html="<p>HTML version</p>")
        result = parse_emlx_body(emlx)
        assert result is not None
        assert "Plain version" in result
        assert "HTML" not in result

    def test_multipart_html_fallback(self, tmp_path: Path):
        """Falls back to text/html when no text/plain in multipart."""
        emlx = tmp_path / "4.emlx"
        _make_multipart_emlx(emlx, text_plain=None, text_html="<p>Only HTML here</p>")
        result = parse_emlx_body(emlx)
        assert result is not None
        assert "Only HTML here" in result
        assert "<p>" not in result

    def test_truncates_to_max_chars(self, tmp_path: Path):
        """Truncates body text to max_chars."""
        emlx = tmp_path / "5.emlx"
        _make_emlx(emlx, b"A" * 10000)
        result = parse_emlx_body(emlx, max_chars=100)
        assert result is not None
        assert len(result) <= 100

    def test_default_max_chars_is_4000(self, tmp_path: Path):
        """Default max_chars is 4000."""
        emlx = tmp_path / "6.emlx"
        _make_emlx(emlx, b"B" * 10000)
        result = parse_emlx_body(emlx)
        assert result is not None
        assert len(result) <= 4000

    def test_charset_utf8(self, tmp_path: Path):
        """Handles utf-8 charset correctly."""
        emlx = tmp_path / "7.emlx"
        _make_emlx(emlx, "Cafe\u0301 au lait".encode("utf-8"), charset="utf-8")
        result = parse_emlx_body(emlx)
        assert result is not None
        assert "Caf" in result

    def test_charset_latin1(self, tmp_path: Path):
        """Handles latin-1 charset with errors='replace'."""
        emlx = tmp_path / "8.emlx"
        _make_emlx(emlx, "R\xe9sum\xe9".encode("latin-1"), charset="latin-1")
        result = parse_emlx_body(emlx)
        assert result is not None
        assert "sum" in result

    def test_charset_windows_1252(self, tmp_path: Path):
        """Handles windows-1252 charset with errors='replace'."""
        emlx = tmp_path / "9.emlx"
        # Build raw .emlx manually with cp1252-encoded body
        body_bytes = b"Smart \x93quotes\x94"
        raw_msg = (
            b"From: test@example.com\r\n"
            b"Subject: Test\r\n"
            b"Content-Type: text/plain; charset=windows-1252\r\n"
            b"Content-Transfer-Encoding: 8bit\r\n"
            b"\r\n"
        ) + body_bytes
        with open(emlx, "wb") as f:
            f.write(f"{len(raw_msg)}\n".encode())
            f.write(raw_msg)
        result = parse_emlx_body(emlx)
        assert result is not None
        assert "quotes" in result


class TestErrorHandling:
    """Tests for graceful degradation on corrupt/missing/binary files."""

    def test_returns_none_for_missing_file(self, tmp_path: Path):
        """Returns None when .emlx file doesn't exist."""
        result = parse_emlx_body(tmp_path / "nonexistent.emlx")
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path: Path):
        """Returns None for an empty file."""
        emlx = tmp_path / "empty.emlx"
        emlx.write_bytes(b"")
        result = parse_emlx_body(emlx)
        assert result is None

    def test_returns_none_for_corrupt_byte_count(self, tmp_path: Path):
        """Returns None when byte count line is not a number."""
        emlx = tmp_path / "corrupt.emlx"
        emlx.write_bytes(b"NOT_A_NUMBER\nsome data\n")
        result = parse_emlx_body(emlx)
        assert result is None

    def test_returns_none_for_binary_content(self, tmp_path: Path):
        """Returns None for binary/non-text content type."""
        emlx = tmp_path / "binary.emlx"
        # Create a message with application/octet-stream
        from email.mime.base import MIMEBase
        msg = MIMEBase("application", "octet-stream")
        msg.set_payload(b"\x00\x01\x02\x03")
        msg["From"] = "test@example.com"
        msg["Subject"] = "Binary"
        msg_bytes = msg.as_bytes()
        with open(emlx, "wb") as f:
            f.write(f"{len(msg_bytes)}\n".encode())
            f.write(msg_bytes)
        result = parse_emlx_body(emlx)
        assert result is None

    def test_returns_none_for_truncated_binary(self, tmp_path: Path):
        """Returns None when truncated file has only binary garbage."""
        emlx = tmp_path / "truncated.emlx"
        emlx.write_bytes(b"99999\n\x00\x01\x02\x03\x04")
        result = parse_emlx_body(emlx)
        # Truncated binary: either None or empty-ish — never crashes
        assert result is None or (isinstance(result, str) and len(result) < 20)
