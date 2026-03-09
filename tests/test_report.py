"""Tests for report generation module."""

from __future__ import annotations

import json
import time
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from icloud_cleanup.models import Classification, Message, Tier
from icloud_cleanup.report import (
    build_report_data,
    export_json_report,
    export_markdown_report,
    generate_report,
    render_terminal_report,
)


def _make_message(
    message_id: int,
    *,
    size: int = 5000,
    date_received: int = 1700000000,
    sender_address: str = "test@example.com",
    subject: str = "Test Subject",
) -> Message:
    return Message(
        rowid=message_id,
        message_id=message_id,
        conversation_id=0,
        flags=0,
        read=0,
        flagged=0,
        deleted=0,
        size=size,
        date_received=date_received,
        sender_address=sender_address,
        subject=subject,
        mailbox_url="imap://test/INBOX",
        list_id_hash=None,
        unsubscribe_type=None,
        automated_conversation=0,
        model_category=None,
        model_high_impact=0,
    )


def _make_classification(
    message_id: int,
    tier: Tier = Tier.REVIEW,
    confidence: float = 0.5,
    *,
    cluster_id: int | None = None,
    cluster_label: str | None = None,
    protected: bool = False,
) -> Classification:
    return Classification(
        message_id=message_id,
        tier=tier,
        confidence=confidence,
        signals="test_signal",
        protected=protected,
        timestamp=int(time.time()),
        cluster_id=cluster_id,
        cluster_label=cluster_label,
    )


class TestBuildReportData:
    """Tests for build_report_data function."""

    def test_groups_by_tier(self) -> None:
        classifications = [
            _make_classification(1, Tier.TRASH, 0.02),
            _make_classification(2, Tier.KEEP_ACTIVE, 0.95),
            _make_classification(3, Tier.REVIEW, 0.5),
            _make_classification(4, Tier.KEEP_HISTORICAL, 0.8),
        ]
        messages = [_make_message(i) for i in range(1, 5)]

        data = build_report_data(classifications, messages)

        assert "tiers" in data
        assert data["total_emails"] == 4
        assert data["tiers"]["trash"]["count"] == 1
        assert data["tiers"]["keep_active"]["count"] == 1
        assert data["tiers"]["review"]["count"] == 1
        assert data["tiers"]["keep_historical"]["count"] == 1

    def test_tier_size_aggregation(self) -> None:
        classifications = [
            _make_classification(1, Tier.TRASH, 0.02),
            _make_classification(2, Tier.TRASH, 0.03),
        ]
        messages = [
            _make_message(1, size=1000),
            _make_message(2, size=2000),
        ]

        data = build_report_data(classifications, messages)
        assert data["tiers"]["trash"]["size"] == 3000

    def test_confidence_stats(self) -> None:
        classifications = [
            _make_classification(1, Tier.REVIEW, 0.2),
            _make_classification(2, Tier.REVIEW, 0.4),
            _make_classification(3, Tier.REVIEW, 0.6),
            _make_classification(4, Tier.REVIEW, 0.8),
        ]
        messages = [_make_message(i) for i in range(1, 5)]

        data = build_report_data(classifications, messages)
        conf = data["tiers"]["review"]["confidence"]
        assert conf["min"] == pytest.approx(0.2)
        assert conf["max"] == pytest.approx(0.8)
        assert conf["mean"] == pytest.approx(0.5)

    def test_cluster_grouping_within_tier(self) -> None:
        classifications = [
            _make_classification(1, Tier.REVIEW, 0.5, cluster_id=0, cluster_label="newsletters"),
            _make_classification(2, Tier.REVIEW, 0.6, cluster_id=0, cluster_label="newsletters"),
            _make_classification(3, Tier.REVIEW, 0.3, cluster_id=1, cluster_label="promotions"),
        ]
        messages = [_make_message(i) for i in range(1, 4)]

        data = build_report_data(classifications, messages)
        clusters = data["tiers"]["review"]["clusters"]
        labels = {c["label"] for c in clusters}
        assert "newsletters" in labels
        assert "promotions" in labels

        newsletters = next(c for c in clusters if c["label"] == "newsletters")
        assert newsletters["count"] == 2

    def test_unclustered_items_grouped(self) -> None:
        classifications = [
            _make_classification(1, Tier.REVIEW, 0.5, cluster_id=None, cluster_label=None),
            _make_classification(2, Tier.REVIEW, 0.6, cluster_id=-1, cluster_label=None),
        ]
        messages = [_make_message(i) for i in range(1, 3)]

        data = build_report_data(classifications, messages)
        clusters = data["tiers"]["review"]["clusters"]
        unclustered = [c for c in clusters if c["label"] == "Unclustered"]
        assert len(unclustered) == 1
        assert unclustered[0]["count"] == 2

    def test_cluster_example_subjects(self) -> None:
        classifications = [
            _make_classification(i, Tier.REVIEW, 0.5, cluster_id=0, cluster_label="news")
            for i in range(1, 8)
        ]
        messages = [_make_message(i, subject=f"Subject {i}") for i in range(1, 8)]

        data = build_report_data(classifications, messages)
        cluster = data["tiers"]["review"]["clusters"][0]
        assert 3 <= len(cluster["example_subjects"]) <= 30

    def test_cluster_sender_breakdown(self) -> None:
        classifications = [
            _make_classification(1, Tier.REVIEW, 0.5, cluster_id=0, cluster_label="news"),
            _make_classification(2, Tier.REVIEW, 0.5, cluster_id=0, cluster_label="news"),
            _make_classification(3, Tier.REVIEW, 0.5, cluster_id=0, cluster_label="news"),
        ]
        messages = [
            _make_message(1, sender_address="a@test.com"),
            _make_message(2, sender_address="a@test.com"),
            _make_message(3, sender_address="b@test.com"),
        ]

        data = build_report_data(classifications, messages)
        cluster = data["tiers"]["review"]["clusters"][0]
        assert "sender_breakdown" in cluster
        assert cluster["sender_breakdown"]["a@test.com"] == 2
        assert cluster["sender_breakdown"]["b@test.com"] == 1

    def test_cluster_date_range(self) -> None:
        classifications = [
            _make_classification(1, Tier.REVIEW, 0.5, cluster_id=0, cluster_label="news"),
            _make_classification(2, Tier.REVIEW, 0.5, cluster_id=0, cluster_label="news"),
        ]
        messages = [
            _make_message(1, date_received=1600000000),
            _make_message(2, date_received=1700000000),
        ]

        data = build_report_data(classifications, messages)
        cluster = data["tiers"]["review"]["clusters"][0]
        assert cluster["date_range"]["earliest"] == 1600000000
        assert cluster["date_range"]["latest"] == 1700000000

    def test_empty_classifications(self) -> None:
        data = build_report_data([], [])
        assert data["total_emails"] == 0
        for tier_data in data["tiers"].values():
            assert tier_data["count"] == 0

    def test_generated_at_present(self) -> None:
        data = build_report_data([], [])
        assert "generated_at" in data


class TestRenderTerminalReport:
    """Tests for Rich terminal report rendering."""

    def test_renders_without_error(self) -> None:
        classifications = [
            _make_classification(1, Tier.TRASH, 0.02),
            _make_classification(2, Tier.KEEP_ACTIVE, 0.95),
            _make_classification(3, Tier.REVIEW, 0.5),
        ]
        messages = [_make_message(i) for i in range(1, 4)]
        data = build_report_data(classifications, messages)

        console = Console(file=StringIO(), force_terminal=True, width=120)
        render_terminal_report(data, console)
        output = console.file.getvalue()
        assert len(output) > 0

    def test_contains_tier_names(self) -> None:
        classifications = [
            _make_classification(1, Tier.TRASH, 0.02),
            _make_classification(2, Tier.REVIEW, 0.5),
        ]
        messages = [_make_message(i) for i in range(1, 3)]
        data = build_report_data(classifications, messages)

        console = Console(file=StringIO(), force_terminal=True, width=120)
        render_terminal_report(data, console)
        output = console.file.getvalue()
        assert "trash" in output.lower()
        assert "review" in output.lower()

    def test_empty_report(self) -> None:
        data = build_report_data([], [])
        console = Console(file=StringIO(), force_terminal=True, width=120)
        render_terminal_report(data, console)
        output = console.file.getvalue()
        assert len(output) > 0


class TestExportJsonReport:
    """Tests for JSON export."""

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        classifications = [
            _make_classification(1, Tier.TRASH, 0.02),
            _make_classification(2, Tier.REVIEW, 0.5),
        ]
        messages = [_make_message(i) for i in range(1, 3)]
        data = build_report_data(classifications, messages)

        out = tmp_path / "report.json"
        result = export_json_report(data, out)

        assert result == out
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded["total_emails"] == 2

    def test_contains_all_tiers(self, tmp_path: Path) -> None:
        data = build_report_data([], [])
        out = tmp_path / "report.json"
        export_json_report(data, out)
        loaded = json.loads(out.read_text())
        assert set(loaded["tiers"].keys()) == {"trash", "keep_active", "keep_historical", "review"}


class TestExportMarkdownReport:
    """Tests for Markdown export."""

    def test_writes_markdown_file(self, tmp_path: Path) -> None:
        classifications = [
            _make_classification(1, Tier.TRASH, 0.02),
            _make_classification(2, Tier.REVIEW, 0.5),
        ]
        messages = [_make_message(i) for i in range(1, 3)]
        data = build_report_data(classifications, messages)

        out = tmp_path / "report.md"
        result = export_markdown_report(data, out)

        assert result == out
        assert out.exists()
        content = out.read_text()
        assert "# iCloud Mail Cleanup Report" in content

    def test_contains_tier_table(self, tmp_path: Path) -> None:
        classifications = [_make_classification(1, Tier.REVIEW, 0.5)]
        messages = [_make_message(1)]
        data = build_report_data(classifications, messages)

        out = tmp_path / "report.md"
        export_markdown_report(data, out)
        content = out.read_text()
        assert "| Tier" in content
        assert "review" in content.lower()

    def test_confidence_bar_in_markdown(self, tmp_path: Path) -> None:
        classifications = [
            _make_classification(i, Tier.REVIEW, 0.3 + i * 0.1)
            for i in range(1, 6)
        ]
        messages = [_make_message(i) for i in range(1, 6)]
        data = build_report_data(classifications, messages)

        out = tmp_path / "report.md"
        export_markdown_report(data, out)
        content = out.read_text()
        # Should contain some unicode block chars for confidence vis
        block_chars = set("█▇▆▅▄▃▂▁")
        assert any(ch in content for ch in block_chars)

    def test_empty_report_markdown(self, tmp_path: Path) -> None:
        data = build_report_data([], [])
        out = tmp_path / "report.md"
        export_markdown_report(data, out)
        assert out.exists()
        content = out.read_text()
        assert "0 emails" in content.lower() or "0" in content


class TestGenerateReport:
    """Tests for the dispatcher function."""

    def test_format_json(self, tmp_path: Path) -> None:
        classifications = [_make_classification(1, Tier.REVIEW, 0.5)]
        messages = [_make_message(1)]

        result = generate_report(classifications, messages, tmp_path, format="json")
        assert "json" in result
        assert (tmp_path / "report.json").exists()

    def test_format_markdown(self, tmp_path: Path) -> None:
        classifications = [_make_classification(1, Tier.REVIEW, 0.5)]
        messages = [_make_message(1)]

        result = generate_report(classifications, messages, tmp_path, format="markdown")
        assert "markdown" in result
        assert (tmp_path / "report.md").exists()

    def test_format_all(self, tmp_path: Path) -> None:
        classifications = [_make_classification(1, Tier.REVIEW, 0.5)]
        messages = [_make_message(1)]

        result = generate_report(classifications, messages, tmp_path, format="all")
        assert (tmp_path / "report.json").exists()
        assert (tmp_path / "report.md").exists()

    def test_format_terminal(self, tmp_path: Path) -> None:
        classifications = [_make_classification(1, Tier.REVIEW, 0.5)]
        messages = [_make_message(1)]

        result = generate_report(classifications, messages, tmp_path, format="terminal")
        assert "terminal" in result
