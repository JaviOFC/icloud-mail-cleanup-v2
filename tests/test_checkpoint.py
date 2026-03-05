"""Tests for checkpoint persistence — JSONL save, load, and merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from icloud_cleanup.models import Classification, Tier
from icloud_cleanup.checkpoint import (
    CHECKPOINT_VERSION,
    load_checkpoint,
    merge_checkpoint,
    save_checkpoint,
)


def _make_classification(
    *,
    message_id: int = 1,
    tier: Tier = Tier.REVIEW,
    confidence: float = 0.5,
    signals: str = "test=0.50",
    protected: bool = False,
    timestamp: int = 1700000000,
) -> Classification:
    """Create a Classification with sensible defaults for testing."""
    return Classification(
        message_id=message_id,
        tier=tier,
        confidence=confidence,
        signals=signals,
        protected=protected,
        timestamp=timestamp,
    )


class TestSaveCheckpoint:
    """Tests for save_checkpoint()."""

    def test_writes_jsonl_file(self, tmp_path: Path):
        """save_checkpoint creates a JSONL file with one JSON object per line."""
        path = tmp_path / "test.jsonl"
        classifications = [
            _make_classification(message_id=1),
            _make_classification(message_id=2),
        ]
        save_checkpoint(classifications, path)
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        # Header + 2 data lines
        assert len(lines) == 3

    def test_data_lines_are_valid_json(self, tmp_path: Path):
        """Each non-header line in the checkpoint is valid JSON."""
        path = tmp_path / "test.jsonl"
        classifications = [
            _make_classification(message_id=1, tier=Tier.TRASH),
            _make_classification(message_id=2, tier=Tier.KEEP_ACTIVE),
        ]
        save_checkpoint(classifications, path)
        lines = path.read_text().strip().split("\n")
        for line in lines:
            if not line.startswith("#"):
                obj = json.loads(line)
                assert "message_id" in obj
                assert "tier" in obj

    def test_tier_serialized_as_string_value(self, tmp_path: Path):
        """Tier is serialized as its string value (e.g., 'trash', 'keep_active')."""
        path = tmp_path / "test.jsonl"
        classifications = [
            _make_classification(message_id=1, tier=Tier.TRASH),
            _make_classification(message_id=2, tier=Tier.KEEP_ACTIVE),
        ]
        save_checkpoint(classifications, path)
        lines = path.read_text().strip().split("\n")
        data_lines = [l for l in lines if not l.startswith("#")]
        obj1 = json.loads(data_lines[0])
        obj2 = json.loads(data_lines[1])
        assert obj1["tier"] == "trash"
        assert obj2["tier"] == "keep_active"

    def test_header_line_with_metadata(self, tmp_path: Path):
        """First line is a header comment with version and count."""
        path = tmp_path / "test.jsonl"
        classifications = [
            _make_classification(message_id=1),
            _make_classification(message_id=2),
            _make_classification(message_id=3),
        ]
        save_checkpoint(classifications, path, scan_timestamp=1700000000)
        header = path.read_text().split("\n")[0]
        assert header.startswith("#")
        assert f"checkpoint_version={CHECKPOINT_VERSION}" in header
        assert "scan_timestamp=1700000000" in header
        assert "count=3" in header

    def test_atomic_write_no_tmp_left(self, tmp_path: Path):
        """Atomic write — .tmp file is cleaned up after save."""
        path = tmp_path / "test.jsonl"
        save_checkpoint([_make_classification()], path)
        tmp_file = Path(str(path) + ".tmp")
        assert not tmp_file.exists()
        assert path.exists()

    def test_atomic_write_uses_rename(self, tmp_path: Path):
        """Verify atomicity by checking the file is complete (not partial)."""
        path = tmp_path / "test.jsonl"
        classifications = [
            _make_classification(message_id=i) for i in range(100)
        ]
        save_checkpoint(classifications, path)
        lines = path.read_text().strip().split("\n")
        data_lines = [l for l in lines if not l.startswith("#")]
        assert len(data_lines) == 100


class TestLoadCheckpoint:
    """Tests for load_checkpoint()."""

    def test_returns_dict_keyed_by_message_id(self, tmp_path: Path):
        """load_checkpoint returns dict[int, Classification]."""
        path = tmp_path / "test.jsonl"
        classifications = [
            _make_classification(message_id=42, tier=Tier.TRASH),
            _make_classification(message_id=99, tier=Tier.KEEP_ACTIVE),
        ]
        save_checkpoint(classifications, path)
        result = load_checkpoint(path)
        assert isinstance(result, dict)
        assert 42 in result
        assert 99 in result
        assert isinstance(result[42], Classification)

    def test_returns_empty_dict_for_missing_file(self, tmp_path: Path):
        """load_checkpoint returns empty dict when file doesn't exist."""
        path = tmp_path / "nonexistent.jsonl"
        result = load_checkpoint(path)
        assert result == {}

    def test_skips_header_lines(self, tmp_path: Path):
        """load_checkpoint skips lines starting with #."""
        path = tmp_path / "test.jsonl"
        save_checkpoint(
            [_make_classification(message_id=1)],
            path,
            scan_timestamp=1700000000,
        )
        result = load_checkpoint(path)
        assert len(result) == 1
        assert 1 in result

    def test_reconstructs_tier_enum(self, tmp_path: Path):
        """Loaded Classification has correct Tier enum value (not string)."""
        path = tmp_path / "test.jsonl"
        save_checkpoint(
            [_make_classification(message_id=1, tier=Tier.KEEP_HISTORICAL)],
            path,
        )
        result = load_checkpoint(path)
        assert result[1].tier == Tier.KEEP_HISTORICAL
        assert isinstance(result[1].tier, Tier)

    def test_roundtrip_preserves_all_fields(self, tmp_path: Path):
        """Save then load returns identical Classification objects."""
        path = tmp_path / "test.jsonl"
        original = _make_classification(
            message_id=42,
            tier=Tier.KEEP_ACTIVE,
            confidence=0.87,
            signals="contact_score=0.90; read_rate=0.75",
            protected=True,
            timestamp=1700123456,
        )
        save_checkpoint([original], path)
        loaded = load_checkpoint(path)
        restored = loaded[42]
        assert restored.message_id == original.message_id
        assert restored.tier == original.tier
        assert restored.confidence == pytest.approx(original.confidence)
        assert restored.signals == original.signals
        assert restored.protected == original.protected
        assert restored.timestamp == original.timestamp

    def test_handles_malformed_lines_gracefully(self, tmp_path: Path):
        """Malformed JSON lines are skipped, valid lines still loaded."""
        path = tmp_path / "test.jsonl"
        content = (
            "# header\n"
            '{"message_id": 1, "tier": "trash", "confidence": 0.5, "signals": "t", "protected": false, "timestamp": 1700000000}\n'
            "NOT VALID JSON\n"
            '{"message_id": 2, "tier": "review", "confidence": 0.6, "signals": "t", "protected": true, "timestamp": 1700000001}\n'
        )
        path.write_text(content)
        result = load_checkpoint(path)
        assert len(result) == 2
        assert 1 in result
        assert 2 in result


class TestMergeCheckpoint:
    """Tests for merge_checkpoint()."""

    def test_new_only_added(self):
        """New classifications not in existing are added."""
        existing = {
            1: _make_classification(message_id=1, timestamp=1000),
        }
        new = [
            _make_classification(message_id=2, timestamp=2000),
            _make_classification(message_id=3, timestamp=2000),
        ]
        result = merge_checkpoint(existing, new)
        ids = {c.message_id for c in result}
        assert ids == {1, 2, 3}

    def test_old_only_preserved(self):
        """Existing classifications not in new set are preserved."""
        existing = {
            1: _make_classification(message_id=1, timestamp=1000),
            2: _make_classification(message_id=2, timestamp=1000),
        }
        new = [
            _make_classification(message_id=3, timestamp=2000),
        ]
        result = merge_checkpoint(existing, new)
        ids = {c.message_id for c in result}
        assert ids == {1, 2, 3}

    def test_conflict_resolved_by_newer_timestamp(self):
        """When message_id exists in both, newer timestamp wins."""
        existing = {
            1: _make_classification(
                message_id=1, tier=Tier.REVIEW, timestamp=1000,
            ),
        }
        new = [
            _make_classification(
                message_id=1, tier=Tier.TRASH, timestamp=2000,
            ),
        ]
        result = merge_checkpoint(existing, new)
        msg1 = next(c for c in result if c.message_id == 1)
        assert msg1.tier == Tier.TRASH
        assert msg1.timestamp == 2000

    def test_conflict_keeps_existing_if_newer(self):
        """When existing has newer timestamp, it wins."""
        existing = {
            1: _make_classification(
                message_id=1, tier=Tier.KEEP_ACTIVE, timestamp=3000,
            ),
        }
        new = [
            _make_classification(
                message_id=1, tier=Tier.TRASH, timestamp=1000,
            ),
        ]
        result = merge_checkpoint(existing, new)
        msg1 = next(c for c in result if c.message_id == 1)
        assert msg1.tier == Tier.KEEP_ACTIVE
        assert msg1.timestamp == 3000

    def test_returns_sorted_by_message_id(self):
        """Result list is sorted by message_id."""
        existing = {
            50: _make_classification(message_id=50),
            10: _make_classification(message_id=10),
        }
        new = [
            _make_classification(message_id=30),
            _make_classification(message_id=5),
        ]
        result = merge_checkpoint(existing, new)
        ids = [c.message_id for c in result]
        assert ids == [5, 10, 30, 50]

    def test_equal_timestamp_new_wins(self):
        """When timestamps are equal, new classification replaces existing."""
        existing = {
            1: _make_classification(
                message_id=1, tier=Tier.REVIEW, timestamp=1000,
            ),
        }
        new = [
            _make_classification(
                message_id=1, tier=Tier.TRASH, timestamp=1000,
            ),
        ]
        result = merge_checkpoint(existing, new)
        msg1 = next(c for c in result if c.message_id == 1)
        assert msg1.tier == Tier.TRASH


class TestRoundTrip:
    """End-to-end round-trip tests."""

    def test_save_load_roundtrip_multiple(self, tmp_path: Path):
        """Save multiple classifications, load, verify all match."""
        path = tmp_path / "roundtrip.jsonl"
        originals = [
            _make_classification(
                message_id=i,
                tier=[Tier.TRASH, Tier.KEEP_ACTIVE, Tier.KEEP_HISTORICAL, Tier.REVIEW][i % 4],
                confidence=i * 0.1,
                signals=f"sig{i}=0.{i}0",
                protected=i % 2 == 0,
                timestamp=1700000000 + i * 100,
            )
            for i in range(10)
        ]
        save_checkpoint(originals, path)
        loaded = load_checkpoint(path)
        assert len(loaded) == 10
        for orig in originals:
            restored = loaded[orig.message_id]
            assert restored.tier == orig.tier
            assert restored.confidence == pytest.approx(orig.confidence)
            assert restored.signals == orig.signals
            assert restored.protected == orig.protected
            assert restored.timestamp == orig.timestamp

    def test_checkpoint_file_is_valid_jsonl(self, tmp_path: Path):
        """Every non-header line in checkpoint file is independently parseable JSON."""
        path = tmp_path / "valid.jsonl"
        save_checkpoint(
            [_make_classification(message_id=i) for i in range(5)],
            path,
        )
        lines = path.read_text().strip().split("\n")
        for line in lines:
            if not line.startswith("#"):
                obj = json.loads(line)
                assert isinstance(obj, dict)
