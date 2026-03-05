---
created: 2026-03-05T05:15:20.457Z
title: Commit classifier tuning fixes and update scoring docs
area: general
files:
  - src/icloud_cleanup/classifier.py
  - tests/test_classifier.py
---

## Problem

During live testing of the Phase 1 classifier against the real Envelope Index (25,135 emails), two issues were found:

1. **TRASH_THRESHOLD too conservative (0.95):** Only 2 emails classified as Trash. The recency signal alone contributes 0.15 to confidence, making it mathematically near-impossible for any recent email to score below 0.05. Lowered to 0.70 (confidence <= 0.30 for trash).

2. **read_rate signal unreliable:** Javi bulk-marked newsletters and old emails as "read" to clear notification badges. With 99.5% of emails marked read, read_rate cannot discriminate engagement. Dropped read_rate_signal entirely and reworked frequency_score to penalize high-volume unknown senders instead of using read_rate. Redistributed 0.15 weight to reply_rate (0.10 -> 0.20) and automation (0.05 -> 0.10).

Final distribution: Trash 22.5%, Keep-Active 0.5%, Keep-Historical 75.7%, Review 1.4%. Zero bidirectional contacts in Trash.

## Solution

Changes are already made in working tree. Need to:
1. Commit the classifier.py and test_classifier.py changes
2. Update CONTEXT.md or planning docs to record the read_rate discovery and weight adjustments
3. Update 01-03-SUMMARY.md to reflect the tuning changes
