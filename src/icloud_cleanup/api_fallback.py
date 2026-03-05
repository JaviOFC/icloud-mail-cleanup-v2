"""Claude API fallback for classifying ambiguous emails via structured metadata."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from anthropic import Anthropic

from icloud_cleanup.models import Classification, Message, Tier

log = logging.getLogger(__name__)

# Haiku 4.5 batch pricing (50% discount)
BATCH_INPUT_COST_PER_TOKEN = 0.50 / 1_000_000   # $0.50/MTok
BATCH_OUTPUT_COST_PER_TOKEN = 2.50 / 1_000_000  # $2.50/MTok
AVG_INPUT_TOKENS_PER_EMAIL = 200
AVG_OUTPUT_TOKENS_PER_EMAIL = 50


def build_metadata_payload(
    classification: Classification,
    message: Message,
    cluster_examples: list[str],
) -> dict:
    """Build a structured metadata summary for API classification.

    Privacy guarantee: never includes body text, HTML, or raw email content.
    """
    dt = datetime.fromtimestamp(message.date_received, tz=timezone.utc)
    return {
        "subject": message.subject,
        "sender_address": message.sender_address,
        "date_received": dt.strftime("%Y-%m-%d"),
        "tier": classification.tier.value,
        "confidence": classification.confidence,
        "cluster_label": classification.cluster_label,
        "cluster_example_subjects": cluster_examples[:5],
        "signals": classification.signals,
    }


def build_classification_prompt(payload: dict) -> tuple[str, str]:
    """Build system and user prompts for email classification.

    Returns (system_prompt, user_message) tuple.
    """
    system = (
        "You are an email classification assistant. Based on the metadata below, "
        "classify this email as trash, keep_active, keep_historical, or review. "
        "Respond with JSON: {\"tier\": \"...\", \"confidence\": 0.0-1.0, \"reason\": \"...\"}."
    )

    parts = [
        f"Subject: {payload['subject']}",
        f"Sender: {payload['sender_address']}",
        f"Date: {payload['date_received']}",
        f"Current tier: {payload['tier']}",
        f"Current confidence: {payload['confidence']}",
    ]
    if payload.get("cluster_label"):
        parts.append(f"Cluster: {payload['cluster_label']}")
    if payload.get("cluster_example_subjects"):
        examples = ", ".join(payload["cluster_example_subjects"])
        parts.append(f"Similar emails in cluster: {examples}")
    if payload.get("signals"):
        parts.append(f"Classification signals: {payload['signals']}")

    user = "\n".join(parts)
    return system, user


def estimate_api_cost(
    email_count: int,
    model: str = "claude-haiku-4-5-20250929",
) -> dict:
    """Estimate token cost for batch classification."""
    total_input = email_count * AVG_INPUT_TOKENS_PER_EMAIL
    total_output = email_count * AVG_OUTPUT_TOKENS_PER_EMAIL

    input_cost = total_input * BATCH_INPUT_COST_PER_TOKEN
    output_cost = total_output * BATCH_OUTPUT_COST_PER_TOKEN

    return {
        "email_count": email_count,
        "estimated_input_tokens": total_input,
        "estimated_output_tokens": total_output,
        "estimated_cost_usd": round(input_cost + output_cost, 4),
        "model": model,
        "pricing_type": "batch (50% discount)",
    }


def classify_ambiguous_batch(
    payloads: list[dict],
    model: str = "claude-haiku-4-5-20250929",
) -> object:
    """Submit metadata payloads to Anthropic Batch API for classification.

    Each payload must include a '_message_id' field for tracking.
    Returns the batch object (caller polls for completion).
    """
    client = Anthropic()

    requests = []
    for payload in payloads:
        message_id = payload["_message_id"]
        system, user = build_classification_prompt(payload)
        requests.append({
            "custom_id": f"msg-{message_id}",
            "params": {
                "model": model,
                "max_tokens": 256,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        })

    batch = client.messages.batches.create(requests=requests)
    return batch


def integrate_api_results(
    batch_results: list[dict],
    existing: dict[int, Classification],
) -> list[Classification]:
    """Update classifications based on API responses.

    Parses batch results, updates tier/confidence, appends 'api_fallback' to signals.
    Skips unknown message IDs and invalid tiers gracefully.
    """
    updated: list[Classification] = []

    for result in batch_results:
        custom_id = result.get("custom_id", "")
        if not custom_id.startswith("msg-"):
            continue

        try:
            message_id = int(custom_id.split("-", 1)[1])
        except (ValueError, IndexError):
            continue

        if message_id not in existing:
            log.warning("API result for unknown message_id: %d", message_id)
            continue

        try:
            new_tier = Tier(result["tier"])
        except ValueError:
            log.warning(
                "Invalid tier '%s' from API for message_id %d",
                result.get("tier"), message_id,
            )
            continue

        cls = existing[message_id]
        new_confidence = float(result.get("confidence", cls.confidence))
        existing_signals = cls.signals or ""
        new_signals = f"{existing_signals},api_fallback" if existing_signals else "api_fallback"

        updated_cls = Classification(
            message_id=cls.message_id,
            tier=new_tier,
            confidence=new_confidence,
            signals=new_signals,
            protected=cls.protected,
            timestamp=int(time.time()),
            content_score=cls.content_score,
            cluster_id=cls.cluster_id,
            cluster_label=cls.cluster_label,
            content_source=cls.content_source,
        )
        updated.append(updated_cls)

    return updated
