"""Tests for executor module: AppleScript generation, action log, dry-run, batch execution."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from icloud_cleanup.executor import (
    ActionLog,
    execute_deletions,
    generate_applescript,
    generate_restore_script,
    restore_from_log,
    url_to_applescript_mailbox,
)
from icloud_cleanup.models import Classification, Message, Tier


# --- Fixtures ---


def _make_message(
    rowid: int = 100,
    message_id: int = 5000,
    mailbox_url: str = "imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/INBOX",
    sender_address: str = "spam@example.com",
    subject: str = "Buy now",
) -> Message:
    return Message(
        rowid=rowid,
        message_id=message_id,
        conversation_id=0,
        flags=0,
        read=0,
        flagged=0,
        deleted=0,
        size=1000,
        date_received=1700000000,
        sender_address=sender_address,
        subject=subject,
        mailbox_url=mailbox_url,
        list_id_hash=None,
        unsubscribe_type=None,
        automated_conversation=0,
        model_category=None,
        model_high_impact=0,
    )


def _make_classification(
    message_id: int = 5000,
    tier: Tier = Tier.TRASH,
    confidence: float = 0.02,
    protected: bool = False,
) -> Classification:
    return Classification(
        message_id=message_id,
        tier=tier,
        confidence=confidence,
        signals="test_signal",
        protected=protected,
        timestamp=int(time.time()),
    )


# --- URL to AppleScript mailbox conversion ---


class TestUrlToApplescriptMailbox:
    def test_inbox(self):
        url = "imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/INBOX"
        result = url_to_applescript_mailbox(url)
        assert result == 'mailbox "INBOX" of account "iCloud"'

    def test_archive(self):
        url = "imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/Archive"
        result = url_to_applescript_mailbox(url)
        assert result == 'mailbox "Archive" of account "iCloud"'

    def test_url_encoded_path(self):
        url = "imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/Deleted%20Messages"
        result = url_to_applescript_mailbox(url)
        assert result == 'mailbox "Deleted Messages" of account "iCloud"'

    def test_nested_folder(self):
        url = "imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/Events/Ice%20Palace%20Events/DeadMau5"
        result = url_to_applescript_mailbox(url)
        assert result == 'mailbox "Events/My Custom Events/DeadMau5" of account "iCloud"'

    def test_sent_messages(self):
        url = "imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/Sent%20Messages"
        result = url_to_applescript_mailbox(url)
        assert result == 'mailbox "Sent Messages" of account "iCloud"'


# --- AppleScript generation ---


class TestGenerateApplescript:
    def test_basic_trash_move(self):
        script = generate_applescript(
            rowid=140941,
            source_mailbox='mailbox "INBOX" of account "iCloud"',
        )
        assert "whose id is 140941" in script
        assert '"INBOX"' in script
        assert '"Deleted Messages"' in script
        assert "set mailbox of" in script
        assert 'tell application "Mail"' in script

    def test_archive_source(self):
        script = generate_applescript(
            rowid=99999,
            source_mailbox='mailbox "Archive" of account "iCloud"',
        )
        assert "whose id is 99999" in script
        assert '"Archive"' in script

    def test_custom_trash_mailbox(self):
        script = generate_applescript(
            rowid=100,
            source_mailbox='mailbox "INBOX" of account "iCloud"',
            trash_mailbox="Custom Trash",
        )
        assert '"Custom Trash"' in script

    def test_no_delete_command(self):
        """AppleScript must use 'set mailbox of', never 'delete'."""
        script = generate_applescript(
            rowid=100,
            source_mailbox='mailbox "INBOX" of account "iCloud"',
        )
        assert "delete" not in script.lower()


class TestGenerateRestoreScript:
    def test_restore_from_trash(self):
        script = generate_restore_script(
            rowid=140941,
            original_mailbox='mailbox "INBOX" of account "iCloud"',
        )
        assert "whose id is 140941" in script
        assert '"Deleted Messages"' in script
        assert '"INBOX"' in script
        assert "set mailbox of" in script


# --- Action Log ---


class TestActionLog:
    def test_creates_db_and_table(self, tmp_path: Path):
        db_path = tmp_path / "action_log.db"
        log = ActionLog(db_path)
        assert db_path.exists()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='action_log'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_creates_indexes(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        conn = sqlite3.connect(tmp_path / "action_log.db")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        index_names = {row[0] for row in cursor}
        assert "idx_action_log_message_id" in index_names
        assert "idx_action_log_timestamp" in index_names
        conn.close()

    def test_log_and_retrieve_action(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=5000,
            rowid_in_db=100,
            subject="Test email",
            sender_address="test@example.com",
            tier="trash",
            confidence=0.02,
            action="move_to_trash",
            source_mailbox="INBOX",
            dry_run=True,
            success=True,
            error_message=None,
        )
        actions = log.get_actions()
        assert len(actions) == 1
        assert actions[0]["message_id"] == 5000
        assert actions[0]["action"] == "move_to_trash"
        assert actions[0]["dry_run"] == 1

    def test_get_actions_filter_by_action(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=1, rowid_in_db=1, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=False, success=True, error_message=None,
        )
        log.log_action(
            message_id=2, rowid_in_db=2, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="restore",
            source_mailbox="INBOX", dry_run=False, success=True, error_message=None,
        )
        trash_actions = log.get_actions(action="move_to_trash")
        assert len(trash_actions) == 1
        assert trash_actions[0]["message_id"] == 1

    def test_get_actions_filter_by_dry_run(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=1, rowid_in_db=1, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=True, success=True, error_message=None,
        )
        log.log_action(
            message_id=2, rowid_in_db=2, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=False, success=True, error_message=None,
        )
        real_actions = log.get_actions(dry_run=False)
        assert len(real_actions) == 1
        assert real_actions[0]["message_id"] == 2

    def test_get_restorable(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        # Successful real move
        log.log_action(
            message_id=1, rowid_in_db=1, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=False, success=True, error_message=None,
        )
        # Dry-run move (should not be restorable)
        log.log_action(
            message_id=2, rowid_in_db=2, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=True, success=True, error_message=None,
        )
        # Failed real move (should not be restorable)
        log.log_action(
            message_id=3, rowid_in_db=3, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=False, success=False, error_message="err",
        )
        restorable = log.get_restorable()
        assert len(restorable) == 1
        assert restorable[0]["message_id"] == 1


# --- Execute deletions ---


class TestExecuteDeletions:
    def test_dry_run_no_subprocess(self, tmp_path: Path):
        """Dry-run mode must NOT call subprocess."""
        msg = _make_message()
        cls = _make_classification()
        log = ActionLog(tmp_path / "action_log.db")

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            result = execute_deletions(
                messages=[msg],
                classifications={msg.message_id: cls},
                action_log=log,
                dry_run=True,
                batch_size=100,
            )
            mock_sub.run.assert_not_called()

        assert result["success_count"] == 1
        assert result["error_count"] == 0

        # Verify action was logged as dry-run
        actions = log.get_actions()
        assert len(actions) == 1
        assert actions[0]["dry_run"] == 1

    def test_real_execution_calls_subprocess(self, tmp_path: Path):
        msg = _make_message()
        cls = _make_classification()
        log = ActionLog(tmp_path / "action_log.db")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            result = execute_deletions(
                messages=[msg],
                classifications={msg.message_id: cls},
                action_log=log,
                dry_run=False,
                batch_size=100,
            )
            mock_sub.run.assert_called_once()

        assert result["success_count"] == 1
        assert result["error_count"] == 0

    def test_protected_message_rejected(self, tmp_path: Path):
        """Protected messages must be skipped with error."""
        msg = _make_message()
        cls = _make_classification(protected=True)
        log = ActionLog(tmp_path / "action_log.db")

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            result = execute_deletions(
                messages=[msg],
                classifications={msg.message_id: cls},
                action_log=log,
                dry_run=False,
                batch_size=100,
            )
            mock_sub.run.assert_not_called()

        assert result["skipped_protected"] == 1
        assert result["success_count"] == 0

    def test_batch_pause_between_batches(self, tmp_path: Path):
        """Should pause between batches."""
        msgs = [_make_message(rowid=i, message_id=5000 + i) for i in range(5)]
        clss = {m.message_id: _make_classification(message_id=m.message_id) for m in msgs}
        log = ActionLog(tmp_path / "action_log.db")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with (
            patch("icloud_cleanup.executor.subprocess") as mock_sub,
            patch("icloud_cleanup.executor.time") as mock_time,
        ):
            mock_sub.run.return_value = mock_result
            result = execute_deletions(
                messages=msgs,
                classifications=clss,
                action_log=log,
                dry_run=False,
                batch_size=2,
                batch_pause=1.0,
            )
            # 5 messages, batch_size=2 -> batches [0:2], [2:4], [4:5]
            # Pause after each batch except the last = 2 pauses
            assert mock_time.sleep.call_count == 2

        assert result["success_count"] == 5

    def test_subprocess_error_logged(self, tmp_path: Path):
        msg = _make_message()
        cls = _make_classification()
        log = ActionLog(tmp_path / "action_log.db")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "AppleScript error"

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            result = execute_deletions(
                messages=[msg],
                classifications={msg.message_id: cls},
                action_log=log,
                dry_run=False,
                batch_size=100,
            )

        assert result["error_count"] == 1
        assert len(result["errors"]) == 1

        actions = log.get_actions()
        assert actions[0]["success"] == 0
        assert actions[0]["error_message"] == "AppleScript error"


# --- Restore from log ---


class TestRestoreFromLog:
    def test_restore_dry_run(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=5000, rowid_in_db=100, subject="Test",
            sender_address="s@e.com", tier="trash", confidence=0.0,
            action="move_to_trash", source_mailbox="INBOX",
            dry_run=False, success=True, error_message=None,
        )

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            result = restore_from_log(log, dry_run=True)
            mock_sub.run.assert_not_called()

        assert result["success_count"] == 1

    def test_restore_real_execution(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=5000, rowid_in_db=100, subject="Test",
            sender_address="s@e.com", tier="trash", confidence=0.0,
            action="move_to_trash", source_mailbox="INBOX",
            dry_run=False, success=True, error_message=None,
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            result = restore_from_log(log, dry_run=False)
            mock_sub.run.assert_called_once()

        assert result["success_count"] == 1
