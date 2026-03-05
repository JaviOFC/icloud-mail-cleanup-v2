"""JSONL checkpoint persistence for classification state."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from icloud_cleanup.models import Classification, Tier

log = logging.getLogger(__name__)

CHECKPOINT_VERSION = 1


def save_checkpoint(
    classifications: list[Classification],
    path: Path,
    scan_timestamp: int | None = None,
) -> None:
    """Save classifications as JSONL with atomic write.

    Writes to a .tmp file first, then renames for atomicity.
    Header line contains version, scan timestamp, and count.
    """
    if scan_timestamp is None:
        scan_timestamp = int(time.time())

    tmp_path = Path(str(path) + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w") as f:
        f.write(
            f"# checkpoint_version={CHECKPOINT_VERSION} "
            f"scan_timestamp={scan_timestamp} "
            f"count={len(classifications)}\n"
        )
        for c in classifications:
            obj = {
                "message_id": c.message_id,
                "tier": c.tier.value,
                "confidence": c.confidence,
                "signals": c.signals,
                "protected": c.protected,
                "timestamp": c.timestamp,
            }
            # Phase 2 optional fields — only write when present
            if c.content_score is not None:
                obj["content_score"] = c.content_score
            if c.cluster_id is not None:
                obj["cluster_id"] = c.cluster_id
            if c.cluster_label is not None:
                obj["cluster_label"] = c.cluster_label
            if c.content_source is not None:
                obj["content_source"] = c.content_source
            f.write(json.dumps(obj) + "\n")

    os.replace(tmp_path, path)


def load_checkpoint(path: Path) -> dict[int, Classification]:
    """Load classifications from a JSONL checkpoint file.

    Returns dict keyed by message_id. Returns empty dict if file
    doesn't exist. Skips header lines (starting with #) and
    malformed JSON lines.
    """
    if not path.exists():
        return {}

    result: dict[int, Classification] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
                c = Classification(
                    message_id=obj["message_id"],
                    tier=Tier(obj["tier"]),
                    confidence=obj["confidence"],
                    signals=obj["signals"],
                    protected=obj["protected"],
                    timestamp=obj["timestamp"],
                    content_score=obj.get("content_score"),
                    cluster_id=obj.get("cluster_id"),
                    cluster_label=obj.get("cluster_label"),
                    content_source=obj.get("content_source"),
                )
                result[c.message_id] = c
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                log.warning("Skipping malformed checkpoint line: %s (%s)", line, exc)
                continue

    return result


def merge_checkpoint(
    existing: dict[int, Classification],
    new: list[Classification],
) -> list[Classification]:
    """Merge new classifications into existing, last-write-wins by timestamp.

    New classifications replace existing ones when message_id matches
    and new.timestamp >= existing.timestamp. Returns sorted list by
    message_id.
    """
    merged = dict(existing)
    for c in new:
        if c.message_id not in merged or c.timestamp >= merged[c.message_id].timestamp:
            merged[c.message_id] = c

    return sorted(merged.values(), key=lambda c: c.message_id)
