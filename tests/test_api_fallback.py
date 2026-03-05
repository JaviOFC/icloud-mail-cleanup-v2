"""Tests for Claude API fallback module: metadata payloads, cost estimation, batch submission, result integration."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from icloud_cleanup.api_fallback import (
    build_classification_prompt,
    build_metadata_payload,
    classify_ambiguous_batch,
    estimate_api_cost,
    integrate_api_results,
)
from icloud_cleanup.models import Classification, Message, Tier


# --- Fixtures ---


def _make_message(
    message_id: int = 5000,
    subject: str = "Weekly Newsletter",
    sender_address: str = "news@example.com",
    date_received: int = 1700000000,
) -> Message:
    return Message(
        rowid=100,
        message_id=message_id,
        conversation_id=0,
        flags=0,
        read=0,
        flagged=0,
        deleted=0,
        size=2000,
        date_received=date_received,
        sender_address=sender_address,
        subject=subject,
        mailbox_url="imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/INBOX",
        list_id_hash=None,
        unsubscribe_type=None,
        automated_conversation=0,
        model_category=None,
        model_high_impact=0,
    )


def _make_classification(
    message_id: int = 5000,
    tier: Tier = Tier.REVIEW,
    confidence: float = 0.45,
    cluster_label: str | None = "newsletters",
) -> Classification:
    return Classification(
        message_id=message_id,
        tier=tier,
        confidence=confidence,
        signals="low_engagement",
        protected=False,
        timestamp=int(time.time()),
        content_score=0.3,
        cluster_id=5,
        cluster_label=cluster_label,
    )


# --- Metadata payload construction ---


class TestBuildMetadataPayload:
    def test_basic_payload_fields(self):
        msg = _make_message()
        cls = _make_classification()
        payload = build_metadata_payload(
            cls, msg, cluster_examples=["Newsletter #1", "Newsletter #2", "Newsletter #3"]
        )
        assert payload["subject"] == "Weekly Newsletter"
        assert payload["sender_address"] == "news@example.com"
        assert payload["tier"] == "review"
        assert payload["confidence"] == 0.45
        assert payload["cluster_label"] == "newsletters"
        assert len(payload["cluster_example_subjects"]) == 3

    def test_no_body_text_in_payload(self):
        """Privacy guarantee: payload must never contain body text."""
        msg = _make_message()
        cls = _make_classification()
        payload = build_metadata_payload(cls, msg, cluster_examples=["Ex1"])
        payload_str = json.dumps(payload).lower()
        # Should not contain common body-text indicators
        assert "body" not in payload
        assert "content" not in payload or payload.get("content") is None
        assert "html" not in payload
        assert "text/plain" not in payload_str
        assert "text/html" not in payload_str

    def test_date_is_human_readable(self):
        msg = _make_message(date_received=1700000000)
        cls = _make_classification()
        payload = build_metadata_payload(cls, msg, cluster_examples=[])
        # Should be a formatted date string, not raw epoch
        assert isinstance(payload["date_received"], str)
        assert "2023" in payload["date_received"]  # 1700000000 = Nov 2023

    def test_signals_included(self):
        msg = _make_message()
        cls = _make_classification()
        payload = build_metadata_payload(cls, msg, cluster_examples=[])
        assert "signals" in payload
        assert payload["signals"] == "low_engagement"


# --- Cost estimation ---


class TestEstimateApiCost:
    def test_basic_cost_calculation(self):
        result = estimate_api_cost(100)
        assert result["email_count"] == 100
        assert result["estimated_input_tokens"] == 20_000  # 100 * 200
        assert result["estimated_output_tokens"] == 5_000   # 100 * 50
        # Cost: 20000 * 0.50/1M + 5000 * 2.50/1M = 0.01 + 0.0125 = 0.0225
        assert abs(result["estimated_cost_usd"] - 0.0225) < 0.001
        assert result["pricing_type"] == "batch (50% discount)"

    def test_single_email(self):
        result = estimate_api_cost(1)
        assert result["email_count"] == 1
        assert result["estimated_input_tokens"] == 200
        assert result["estimated_output_tokens"] == 50

    def test_large_batch(self):
        result = estimate_api_cost(5000)
        assert result["email_count"] == 5000
        # 5000 * 200 = 1M input, 5000 * 50 = 250K output
        # Cost: 1M * 0.50/1M + 250K * 2.50/1M = 0.50 + 0.625 = 1.125
        assert abs(result["estimated_cost_usd"] - 1.125) < 0.001

    def test_model_field(self):
        result = estimate_api_cost(10, model="claude-haiku-4-5-20250929")
        assert result["model"] == "claude-haiku-4-5-20250929"


# --- Prompt construction ---


class TestBuildClassificationPrompt:
    def test_prompt_contains_metadata(self):
        payload = {
            "subject": "Weekly Newsletter",
            "sender_address": "news@example.com",
            "date_received": "2023-11-14",
            "tier": "review",
            "confidence": 0.45,
            "cluster_label": "newsletters",
            "cluster_example_subjects": ["Newsletter #1"],
            "signals": "low_engagement",
        }
        system, user = build_classification_prompt(payload)
        assert "classify" in system.lower() or "classification" in system.lower()
        assert "Weekly Newsletter" in user
        assert "news@example.com" in user
        assert "JSON" in system

    def test_prompt_requests_json_response(self):
        payload = {
            "subject": "Test",
            "sender_address": "t@e.com",
            "date_received": "2023-11-14",
            "tier": "review",
            "confidence": 0.5,
            "cluster_label": None,
            "cluster_example_subjects": [],
            "signals": "",
        }
        system, user = build_classification_prompt(payload)
        assert "tier" in system.lower()
        assert "confidence" in system.lower()


# --- Batch submission ---


class TestClassifyAmbiguousBatch:
    def test_builds_correct_request_format(self):
        payloads = [
            {"subject": "Test", "sender_address": "a@b.com", "date_received": "2023-11-14",
             "tier": "review", "confidence": 0.5, "cluster_label": None,
             "cluster_example_subjects": [], "signals": "", "_message_id": 5000},
        ]

        mock_client = MagicMock()
        mock_batch = MagicMock()
        mock_client.messages.batches.create.return_value = mock_batch

        with patch("icloud_cleanup.api_fallback.Anthropic", return_value=mock_client):
            result = classify_ambiguous_batch(payloads)

        call_args = mock_client.messages.batches.create.call_args
        requests = call_args.kwargs["requests"]
        assert len(requests) == 1
        assert requests[0]["custom_id"] == "msg-5000"
        assert requests[0]["params"]["model"] == "claude-haiku-4-5-20250929"
        assert requests[0]["params"]["max_tokens"] == 256

    def test_multiple_payloads(self):
        payloads = [
            {"subject": f"Test {i}", "sender_address": f"a{i}@b.com",
             "date_received": "2023-11-14", "tier": "review", "confidence": 0.5,
             "cluster_label": None, "cluster_example_subjects": [],
             "signals": "", "_message_id": 5000 + i}
            for i in range(3)
        ]

        mock_client = MagicMock()
        mock_batch = MagicMock()
        mock_client.messages.batches.create.return_value = mock_batch

        with patch("icloud_cleanup.api_fallback.Anthropic", return_value=mock_client):
            classify_ambiguous_batch(payloads)

        call_args = mock_client.messages.batches.create.call_args
        requests = call_args.kwargs["requests"]
        assert len(requests) == 3
        custom_ids = {r["custom_id"] for r in requests}
        assert custom_ids == {"msg-5000", "msg-5001", "msg-5002"}


# --- Result integration ---


class TestIntegrateApiResults:
    def test_updates_classification_tier(self):
        existing = {
            5000: _make_classification(message_id=5000, tier=Tier.REVIEW, confidence=0.45),
        }
        batch_results = [
            {"custom_id": "msg-5000", "tier": "trash", "confidence": 0.85, "reason": "Promotional newsletter"},
        ]
        updated = integrate_api_results(batch_results, existing)
        assert len(updated) == 1
        assert updated[0].tier == Tier.TRASH
        assert updated[0].confidence == 0.85
        assert "api_fallback" in updated[0].signals

    def test_skips_unknown_message_ids(self):
        existing = {
            5000: _make_classification(message_id=5000),
        }
        batch_results = [
            {"custom_id": "msg-9999", "tier": "trash", "confidence": 0.9, "reason": "Junk"},
        ]
        updated = integrate_api_results(batch_results, existing)
        assert len(updated) == 0

    def test_preserves_original_on_parse_error(self):
        existing = {
            5000: _make_classification(message_id=5000, tier=Tier.REVIEW),
        }
        batch_results = [
            {"custom_id": "msg-5000", "tier": "invalid_tier", "confidence": 0.9, "reason": ""},
        ]
        updated = integrate_api_results(batch_results, existing)
        # Should skip invalid tier gracefully
        assert len(updated) == 0

    def test_multiple_results_integrated(self):
        existing = {
            5000: _make_classification(message_id=5000, tier=Tier.REVIEW),
            5001: _make_classification(message_id=5001, tier=Tier.REVIEW),
        }
        batch_results = [
            {"custom_id": "msg-5000", "tier": "trash", "confidence": 0.9, "reason": "Spam"},
            {"custom_id": "msg-5001", "tier": "keep_active", "confidence": 0.8, "reason": "Personal"},
        ]
        updated = integrate_api_results(batch_results, existing)
        assert len(updated) == 2
        tiers = {c.message_id: c.tier for c in updated}
        assert tiers[5000] == Tier.TRASH
        assert tiers[5001] == Tier.KEEP_ACTIVE
