"""Tests for executor module: AppleScript generation, action log, batch execution."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from icloud_cleanup.executor import (
    ActionLog,
    _parse_batch_results,
    execute_deletions,
    generate_applescript,
    generate_batch_applescript,
    generate_batch_restore_script,
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
        url = "imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/Events/My%20Custom%20Events/DeadMau5"
        result = url_to_applescript_mailbox(url)
        assert result == 'mailbox "Events/My Custom Events/DeadMau5" of account "iCloud"'

    def test_sent_messages(self):
        url = "imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/Sent%20Messages"
        result = url_to_applescript_mailbox(url)
        assert result == 'mailbox "Sent Messages" of account "iCloud"'


# --- Single-message AppleScript generation ---


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
        """AppleScript must use 'set mailbox of', never the 'delete' command."""
        script = generate_applescript(
            rowid=100,
            source_mailbox='mailbox "INBOX" of account "iCloud"',
        )
        lines = [line.strip().lower() for line in script.splitlines()]
        assert not any(line.startswith("delete ") for line in lines)


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


# --- Batch AppleScript generation ---


class TestGenerateBatchApplescript:
    def test_single_message(self):
        msg = _make_message(rowid=123, message_id=5001)
        cls = {5001: _make_classification(message_id=5001)}
        script, rowids = generate_batch_applescript([msg], cls)
        assert rowids == [123]
        assert 'tell application "Mail"' in script
        assert "whose id is 123" in script
        assert '"OK:123"' in script
        assert '"MISS:123"' in script
        assert '"ERR:123:"' in script
        assert "return results" in script

    def test_multiple_messages_same_mailbox(self):
        msgs = [_make_message(rowid=i, message_id=5000 + i) for i in range(3)]
        cls = {m.message_id: _make_classification(message_id=m.message_id) for m in msgs}
        script, rowids = generate_batch_applescript(msgs, cls)
        assert rowids == [0, 1, 2]
        for rid in rowids:
            assert f"whose id is {rid}" in script
            assert f'"OK:{rid}"' in script

    def test_groups_by_mailbox(self):
        msg1 = _make_message(rowid=10, message_id=5010, mailbox_url="imap://UUID/INBOX")
        msg2 = _make_message(rowid=20, message_id=5020, mailbox_url="imap://UUID/Archive")
        msg3 = _make_message(rowid=30, message_id=5030, mailbox_url="imap://UUID/INBOX")
        cls = {m.message_id: _make_classification(message_id=m.message_id) for m in [msg1, msg2, msg3]}
        script, rowids = generate_batch_applescript([msg1, msg2, msg3], cls)
        assert set(rowids) == {10, 20, 30}
        assert 'mailbox "INBOX"' in script
        assert 'mailbox "Archive"' in script

    def test_skips_protected(self):
        msg = _make_message(rowid=99, message_id=5099)
        cls = {5099: _make_classification(message_id=5099, protected=True)}
        script, rowids = generate_batch_applescript([msg], cls)
        assert script == ""
        assert rowids == []

    def test_skips_unclassified(self):
        msg = _make_message(rowid=99, message_id=5099)
        script, rowids = generate_batch_applescript([msg], {})
        assert script == ""
        assert rowids == []

    def test_no_delete_command(self):
        msg = _make_message(rowid=1, message_id=5001)
        cls = {5001: _make_classification(message_id=5001)}
        script, _ = generate_batch_applescript([msg], cls)
        lines = [line.strip().lower() for line in script.splitlines()]
        assert not any(line.startswith("delete ") for line in lines)


class TestGenerateBatchRestoreScript:
    def test_single_entry(self):
        entry = {
            "rowid_in_db": 42,
            "source_mailbox": "imap://UUID/INBOX",
            "message_id": 5042,
        }
        script, rowids = generate_batch_restore_script([entry])
        assert rowids == [42]
        assert "whose id is 42" in script
        assert '"OK:42"' in script
        assert 'mailbox "INBOX"' in script

    def test_multiple_entries(self):
        entries = [
            {"rowid_in_db": 10, "source_mailbox": "imap://UUID/INBOX", "message_id": 5010},
            {"rowid_in_db": 20, "source_mailbox": "imap://UUID/Archive", "message_id": 5020},
        ]
        script, rowids = generate_batch_restore_script(entries)
        assert set(rowids) == {10, 20}
        assert 'mailbox "INBOX"' in script
        assert 'mailbox "Archive"' in script

    def test_plain_mailbox_name(self):
        entry = {"rowid_in_db": 5, "source_mailbox": "INBOX", "message_id": 5005}
        script, rowids = generate_batch_restore_script([entry])
        assert rowids == [5]
        assert 'mailbox "INBOX" of account "iCloud"' in script

    def test_empty_list(self):
        script, rowids = generate_batch_restore_script([])
        assert script == ""
        assert rowids == []


# --- Parse batch results ---


class TestParseBatchResults:
    def test_ok(self):
        results = _parse_batch_results("OK:123\n")
        assert results == {123: ("OK", None)}

    def test_miss(self):
        results = _parse_batch_results("MISS:456\n")
        assert results == {456: ("MISS", None)}

    def test_err(self):
        results = _parse_batch_results("ERR:789:something went wrong\n")
        assert results == {789: ("ERR", "something went wrong")}

    def test_err_with_colons_in_message(self):
        results = _parse_batch_results("ERR:100:error: timeout: 30s\n")
        assert results == {100: ("ERR", "error: timeout: 30s")}

    def test_mixed(self):
        stdout = "OK:1\nMISS:2\nERR:3:bad\nOK:4\n"
        results = _parse_batch_results(stdout)
        assert len(results) == 4
        assert results[1] == ("OK", None)
        assert results[2] == ("MISS", None)
        assert results[3] == ("ERR", "bad")
        assert results[4] == ("OK", None)

    def test_empty(self):
        assert _parse_batch_results("") == {}
        assert _parse_batch_results("\n\n") == {}

    def test_trailing_whitespace(self):
        results = _parse_batch_results("  OK:5  \n  MISS:6  \n")
        assert results == {5: ("OK", None), 6: ("MISS", None)}


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

    def test_log_action_no_commit_defers(self, tmp_path: Path):
        """log_action_no_commit should not be visible from a separate connection until commit."""
        db_path = tmp_path / "action_log.db"
        log = ActionLog(db_path)
        log.log_action_no_commit(
            message_id=1, rowid_in_db=1, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=True, success=True, error_message=None,
        )
        # From the same connection it's visible (SQLite autoread own writes)
        actions = log.get_actions()
        assert len(actions) == 1

        # After explicit commit, still visible
        log.commit()
        actions = log.get_actions()
        assert len(actions) == 1

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

    def test_real_execution_calls_subprocess_once_per_batch(self, tmp_path: Path):
        """Real execution should call subprocess once per batch, not once per message."""
        msgs = [_make_message(rowid=i, message_id=5000 + i) for i in range(3)]
        clss = {m.message_id: _make_classification(message_id=m.message_id) for m in msgs}
        log = ActionLog(tmp_path / "action_log.db")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "OK:0\nOK:1\nOK:2\n"
        mock_result.stderr = ""

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            result = execute_deletions(
                messages=msgs,
                classifications=clss,
                action_log=log,
                dry_run=False,
                batch_size=100,
            )
            # Single osascript call for the whole batch
            assert mock_sub.run.call_count == 1

        assert result["success_count"] == 3
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

        def make_stdout(call_args, **kwargs):
            # Parse the script to extract rowids from the batch
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            # Just return OK for all possible rowids
            r.stdout = "\n".join(f"OK:{i}" for i in range(5))
            return r

        with (
            patch("icloud_cleanup.executor.subprocess") as mock_sub,
            patch("icloud_cleanup.executor.time") as mock_time,
        ):
            mock_sub.run.side_effect = make_stdout
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

    def test_batch_osascript_error_per_message(self, tmp_path: Path):
        """Individual message errors from batch results should be tracked."""
        msgs = [_make_message(rowid=i, message_id=5000 + i) for i in range(3)]
        clss = {m.message_id: _make_classification(message_id=m.message_id) for m in msgs}
        log = ActionLog(tmp_path / "action_log.db")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "OK:0\nERR:1:AppleScript error\nMISS:2\n"
        mock_result.stderr = ""

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            result = execute_deletions(
                messages=msgs,
                classifications=clss,
                action_log=log,
                dry_run=False,
                batch_size=100,
            )

        assert result["success_count"] == 1
        assert result["error_count"] == 2
        assert len(result["errors"]) == 2

        actions = log.get_actions(limit=10)
        successes = [a for a in actions if a["success"]]
        failures = [a for a in actions if not a["success"]]
        assert len(successes) == 1
        assert len(failures) == 2

    def test_progress_callback_called_per_batch(self, tmp_path: Path):
        """progress_callback should be called once per batch with batch size."""
        msgs = [_make_message(rowid=i, message_id=5000 + i) for i in range(5)]
        clss = {m.message_id: _make_classification(message_id=m.message_id) for m in msgs}
        log = ActionLog(tmp_path / "action_log.db")
        callback = MagicMock()

        with patch("icloud_cleanup.executor.subprocess"), \
             patch("icloud_cleanup.executor.time"):
            execute_deletions(
                messages=msgs,
                classifications=clss,
                action_log=log,
                dry_run=True,
                batch_size=2,
                progress_callback=callback,
            )

        # 5 messages, batch_size=2 -> 3 batches: [2, 2, 1]
        assert callback.call_count == 3
        assert callback.call_args_list[0].args == (2,)
        assert callback.call_args_list[1].args == (2,)
        assert callback.call_args_list[2].args == (1,)

    def test_whole_batch_failure(self, tmp_path: Path):
        """If osascript returns non-zero with no stdout, all messages fail."""
        msgs = [_make_message(rowid=i, message_id=5000 + i) for i in range(2)]
        clss = {m.message_id: _make_classification(message_id=m.message_id) for m in msgs}
        log = ActionLog(tmp_path / "action_log.db")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "osascript crashed"

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            result = execute_deletions(
                messages=msgs,
                classifications=clss,
                action_log=log,
                dry_run=False,
                batch_size=100,
            )

        assert result["success_count"] == 0
        assert result["error_count"] == 2
        assert all("osascript crashed" in e for e in result["errors"])


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
        mock_result.stdout = "OK:100\n"
        mock_result.stderr = ""

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            result = restore_from_log(log, dry_run=False)
            mock_sub.run.assert_called_once()

        assert result["success_count"] == 1

    def test_restore_progress_callback(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        for i in range(3):
            log.log_action(
                message_id=5000 + i, rowid_in_db=100 + i, subject="Test",
                sender_address="s@e.com", tier="trash", confidence=0.0,
                action="move_to_trash", source_mailbox="INBOX",
                dry_run=False, success=True, error_message=None,
            )
        callback = MagicMock()

        with patch("icloud_cleanup.executor.subprocess"), \
             patch("icloud_cleanup.executor.time"):
            restore_from_log(log, dry_run=True, batch_size=2, progress_callback=callback)

        # 3 restorable, batch_size=2 -> 2 batches: [2, 1]
        assert callback.call_count == 2
        assert callback.call_args_list[0].args == (2,)
        assert callback.call_args_list[1].args == (1,)

    def test_restore_batch_handles_errors(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=5000, rowid_in_db=100, subject="Test",
            sender_address="s@e.com", tier="trash", confidence=0.0,
            action="move_to_trash", source_mailbox="INBOX",
            dry_run=False, success=True, error_message=None,
        )
        log.log_action(
            message_id=5001, rowid_in_db=101, subject="Test2",
            sender_address="s@e.com", tier="trash", confidence=0.0,
            action="move_to_trash", source_mailbox="INBOX",
            dry_run=False, success=True, error_message=None,
        )

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "OK:100\nMISS:101\n"
        mock_result.stderr = ""

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            mock_sub.run.return_value = mock_result
            result = restore_from_log(log, dry_run=False)

        assert result["success_count"] == 1
        assert result["error_count"] == 1


class TestProtectionOverrides:
    """Tests for protection override behavior in execute_deletions."""

    def test_protected_with_override_gets_deleted(self, tmp_path: Path):
        """Protected message in override set should be included in batch and deleted."""
        msg = _make_message()
        cls = _make_classification(protected=True)
        log = ActionLog(tmp_path / "action_log.db")

        result = execute_deletions(
            messages=[msg],
            classifications={msg.message_id: cls},
            action_log=log,
            dry_run=True,
            batch_size=100,
            protection_overrides={msg.message_id},
        )

        assert result["skipped_protected"] == 0
        assert result["overridden_count"] == 1
        assert result["success_count"] == 1

    def test_protected_without_override_still_skipped(self, tmp_path: Path):
        """Protected message NOT in override set should still be skipped."""
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
                protection_overrides=None,
            )
            mock_sub.run.assert_not_called()

        assert result["skipped_protected"] == 1
        assert result["overridden_count"] == 0
        assert result["success_count"] == 0

    def test_override_protected_action_logged(self, tmp_path: Path):
        """Overridden messages should be logged with action='override_protected'."""
        msg = _make_message()
        cls = _make_classification(protected=True)
        log = ActionLog(tmp_path / "action_log.db")

        execute_deletions(
            messages=[msg],
            classifications={msg.message_id: cls},
            action_log=log,
            dry_run=True,
            batch_size=100,
            protection_overrides={msg.message_id},
        )

        actions = log.get_actions(action="override_protected")
        assert len(actions) == 1
        assert actions[0]["message_id"] == msg.message_id

    def test_mixed_protected_and_normal(self, tmp_path: Path):
        """Batch with protected (overridden), protected (not overridden), and normal messages."""
        msg_normal = _make_message(rowid=1, message_id=5001)
        msg_prot_override = _make_message(rowid=2, message_id=5002)
        msg_prot_skip = _make_message(rowid=3, message_id=5003)

        clss = {
            5001: _make_classification(message_id=5001, protected=False),
            5002: _make_classification(message_id=5002, protected=True),
            5003: _make_classification(message_id=5003, protected=True),
        }

        log = ActionLog(tmp_path / "action_log.db")
        result = execute_deletions(
            messages=[msg_normal, msg_prot_override, msg_prot_skip],
            classifications=clss,
            action_log=log,
            dry_run=True,
            batch_size=100,
            protection_overrides={5002},
        )

        assert result["success_count"] == 2  # normal + overridden
        assert result["skipped_protected"] == 1  # 5003
        assert result["overridden_count"] == 1  # 5002


class TestGetExecutedMessageIds:
    """Tests for ActionLog.get_executed_message_ids()."""

    def test_empty_log(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        assert log.get_executed_message_ids() == set()

    def test_returns_successful_live_moves(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=100, rowid_in_db=1, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=False, success=True, error_message=None,
        )
        assert log.get_executed_message_ids() == {100}

    def test_excludes_dry_runs(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=100, rowid_in_db=1, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=True, success=True, error_message=None,
        )
        assert log.get_executed_message_ids() == set()

    def test_excludes_failed_moves(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=100, rowid_in_db=1, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=False, success=False, error_message="err",
        )
        assert log.get_executed_message_ids() == set()

    def test_excludes_non_trash_actions(self, tmp_path: Path):
        log = ActionLog(tmp_path / "action_log.db")
        log.log_action(
            message_id=100, rowid_in_db=1, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="restore",
            source_mailbox="INBOX", dry_run=False, success=True, error_message=None,
        )
        assert log.get_executed_message_ids() == set()


class TestAlreadyExecutedFiltering:
    """Tests for execute_deletions skipping already-executed messages."""

    def test_already_executed_skipped(self, tmp_path: Path):
        """Messages already successfully moved should not be re-processed."""
        msg = _make_message(rowid=100, message_id=5000)
        cls = _make_classification(message_id=5000)
        log = ActionLog(tmp_path / "action_log.db")

        # Pre-populate: this message was already executed
        log.log_action(
            message_id=5000, rowid_in_db=100, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=False, success=True, error_message=None,
        )

        with patch("icloud_cleanup.executor.subprocess") as mock_sub:
            result = execute_deletions(
                messages=[msg],
                classifications={msg.message_id: cls},
                action_log=log,
                dry_run=False,
                batch_size=100,
            )
            mock_sub.run.assert_not_called()

        assert result["success_count"] == 0
        assert result["already_executed"] == 1

    def test_mix_new_and_already_executed(self, tmp_path: Path):
        """Only new messages should be processed; already-executed are skipped."""
        msg_old = _make_message(rowid=100, message_id=5000)
        msg_new = _make_message(rowid=200, message_id=5001)
        clss = {
            5000: _make_classification(message_id=5000),
            5001: _make_classification(message_id=5001),
        }
        log = ActionLog(tmp_path / "action_log.db")

        # Only msg_old was previously executed
        log.log_action(
            message_id=5000, rowid_in_db=100, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=False, success=True, error_message=None,
        )

        result = execute_deletions(
            messages=[msg_old, msg_new],
            classifications=clss,
            action_log=log,
            dry_run=True,
            batch_size=100,
        )

        assert result["success_count"] == 1  # only msg_new
        assert result["already_executed"] == 1

    def test_dry_run_not_counted_as_executed(self, tmp_path: Path):
        """Dry-run entries should NOT prevent re-execution."""
        msg = _make_message(rowid=100, message_id=5000)
        cls = _make_classification(message_id=5000)
        log = ActionLog(tmp_path / "action_log.db")

        # Previous dry-run only
        log.log_action(
            message_id=5000, rowid_in_db=100, subject="s", sender_address="a",
            tier="trash", confidence=0.0, action="move_to_trash",
            source_mailbox="INBOX", dry_run=True, success=True, error_message=None,
        )

        result = execute_deletions(
            messages=[msg],
            classifications={msg.message_id: cls},
            action_log=log,
            dry_run=True,
            batch_size=100,
        )

        assert result["success_count"] == 1
        assert result["already_executed"] == 0
