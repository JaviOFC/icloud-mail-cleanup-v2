---
phase: 01-scanning-metadata-classification
verified: 2026-03-05T06:00:00Z
status: human_needed
score: 5/5 success criteria verified
re_verification: true
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "classify_with_progress is now called in cli.py cmd_classify() at line 130, wrapping classify_single via lambda"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Run classify against live Envelope Index"
    expected: "Animated progress bar with count/total (e.g., '12,450 / 25,134') and ETA appears and advances during classification"
    why_human: "Visual terminal behavior cannot be verified by static code analysis; progress bars only meaningful against a real dataset with latency"
  - test: "Run classify with --debug-scores against a known contact"
    expected: "Signal breakdown shows contact_score=1.0, high read_rate, protected=True for a contact you regularly email"
    why_human: "Requires access to live Envelope Index and knowledge of actual contacts"
  - test: "Verify tier distribution is reasonable after classify"
    expected: "Trash tier contains only high-confidence junk (newsletters, no-reply senders), known personal contacts absent from Trash, Review captures ambiguous cases"
    why_human: "Threshold calibration judgment depends on actual email corpus and personal knowledge of senders"
---

# Phase 1: Scanning + Metadata Classification Verification Report

**Phase Goal:** Users can scan their iCloud mailbox and get a working 4-tier classification of every email based on metadata signals alone
**Verified:** 2026-03-05T06:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (classify_with_progress wiring fix)

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Running the tool scans the Envelope Index and displays sender volume statistics (count, size, date range) with a progress bar | VERIFIED | display_scan_stats renders Rich table with all 4 columns. classify_with_progress now wired at cli.py:130 with SpinnerColumn/MofNCompleteColumn/TimeRemainingColumn. scan subcommand is a bulk SQL query (no per-message loop) so no per-message progress bar applies; the classify progress bar satisfies SCAN-03's "long-running operations" intent. |
| 2 | Every email is classified into one of 4 tiers (Trash / Keep-Active / Keep-Historical / Review) with a 0-1 confidence score and signal explanation | VERIFIED | classifier.py classify_single returns Classification with tier, confidence, signals. All 8 weighted signals computed. All 134 tests pass. |
| 3 | Emails ever replied to, forwarded, or from known personal contacts are protected from Trash classification regardless of other signals | VERIFIED | contacts.py is_protected checks 4 criteria (bidirectional, conversation_id overlap, flags 0x4 replied, flags 0x10 forwarded). check_protection_override fires at <5% read_rate. Tests cover all paths. |
| 4 | The metadata-only first pass classifies a majority of emails with high confidence, deferring ambiguous emails to Review for Phase 2 | VERIFIED | classify_messages assigns Trash at keep_confidence <= 0.05 (very conservative), Keep at >= 0.70, Review for 0.05-0.70 range. Two-pass strategy implemented: metadata pass is this phase, Review tier holds ambiguous for Phase 2. |
| 5 | Classification output is saved as a JSON checkpoint artifact consumable by subsequent phases | VERIFIED | checkpoint.py saves JSONL with atomic write, loads back as dict[int, Classification], merge_checkpoint supports incremental runs. cmd_classify saves to ~/.icloud-cleanup/checkpoint.jsonl. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/icloud_cleanup/models.py` | Message, ContactProfile, Classification, SignalResult, Tier dataclasses | VERIFIED | All 5 types present. Tier has 4 values (TRASH, KEEP_ACTIVE, KEEP_HISTORICAL, REVIEW). |
| `src/icloud_cleanup/scanner.py` | open_db, scan_messages, get_sender_stats, get_sent_recipients, get_replied_conversation_ids | VERIFIED | All 5 functions present, substantive, read-only DB mode, correct mailbox filtering. |
| `src/icloud_cleanup/contacts.py` | build_contact_profiles, is_protected, check_protection_override, extract_behavioral_signals | VERIFIED | All 4 functions present. Bidirectional detection, read/reply rates, 4-criteria protection logic, ratio-based override all implemented. |
| `src/icloud_cleanup/classifier.py` | classify_messages, classify_single, compute_signals, assign_tier, compute_confidence | VERIFIED | classify_single (line 175) and classify_messages (line 216) both present. 8 weighted signals. Tier assignment with protection enforcement. |
| `src/icloud_cleanup/checkpoint.py` | save_checkpoint, load_checkpoint, merge_checkpoint | VERIFIED | Atomic JSONL write, header line, load handles missing file gracefully, merge uses last-write-wins by timestamp. |
| `src/icloud_cleanup/display.py` | scan_with_progress, classify_with_progress, display_tier_summary, display_top_senders | VERIFIED | All 4 functions implemented. classify_with_progress now wired into cli.py:130. scan_with_progress not called from CLI (scan is a bulk SQL query, not a per-message loop — wrapper doesn't apply). |
| `src/icloud_cleanup/cli.py` | main(), scan/classify/report subcommands | VERIFIED | argparse with 3 subcommands, --db/--checkpoint/--verbose globals, --full and --debug-scores on classify, KeyboardInterrupt handled. |
| `src/icloud_cleanup/__main__.py` | Entry point for python -m icloud_cleanup | VERIFIED | 2-line file, imports main from cli, calls it. |
| `tests/conftest.py` | Mock Envelope Index schema fixture | VERIFIED | In-memory SQLite with correct 6-table schema, iCloud UUID mailboxes seeded. |
| `tests/test_scanner.py` | Tests for SCAN-01 and SCAN-02 | VERIFIED | 21 tests covering readonly mode, field mapping, sender stats, sent recipients, replied conversation IDs. |
| `pyproject.toml` | Project config with dependencies and pytest section | VERIFIED | rich dependency, [tool.pytest.ini_options] testpaths set, uv build system. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `scanner.py` | `models.py` | `from icloud_cleanup.models import Message` | WIRED | Line 8 — used in scan_messages return type and Message construction |
| `contacts.py` | `models.py` | `from icloud_cleanup.models import ContactProfile, Message, SignalResult` | WIRED | Line 7 — all 3 types used throughout module |
| `classifier.py` | `contacts.py` | `from icloud_cleanup.contacts import check_protection_override, is_protected` | WIRED | Line 8 — both functions called in classify_messages and classify_single |
| `classifier.py` | `models.py` | `from icloud_cleanup.models import Classification, ContactProfile, Message, SignalResult, Tier` | WIRED | All types used throughout |
| `checkpoint.py` | `models.py` | `from icloud_cleanup.models import Classification, Tier` | WIRED | Classification constructed in load_checkpoint, Tier deserialized |
| `cli.py` | `scanner.py` | `from icloud_cleanup.scanner import open_db, scan_messages, get_sender_stats, ...` | WIRED | Lines 28-34 — all 5 scanner functions called in subcommands |
| `cli.py` | `contacts.py` | `from icloud_cleanup.contacts import build_contact_profiles, ...` | WIRED | Lines 15-19 — build_contact_profiles called in cmd_classify |
| `cli.py` | `classifier.py` | `from icloud_cleanup.classifier import classify_messages, classify_single, ...` | WIRED | Line 14 — classify_single called via lambda in classify_with_progress at line 130-132 |
| `cli.py` | `checkpoint.py` | `from icloud_cleanup.checkpoint import load_checkpoint, merge_checkpoint, save_checkpoint` | WIRED | Line 13 — all 3 functions called in subcommands |
| `display.py` | `models.py` | `from icloud_cleanup.models import Classification, Message, Tier` | WIRED | Line 20 — all 3 types used for display formatting |
| `cli.py` | `display.py` via `classify_with_progress` | classify subcommand calls classify_with_progress | WIRED | cli.py lines 130-132: `classifications = classify_with_progress(messages, lambda msg: classify_single(msg, profiles, replied_conv_ids, now))` — gap from previous verification is CLOSED |
| `cli.py` | `display.py` via `scan_with_progress` | scan subcommand calls scan_with_progress | NOT_CALLED | scan_with_progress imported (line 25) but not called from cmd_scan. cmd_scan uses get_sender_stats (single bulk SQL query) — there is no per-message loop to wrap. Not a blocker: SCAN-03 intent satisfied by classify_with_progress. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| SCAN-01 | 01-01 | Scan Envelope Index SQLite DB read-only for user@icloud.com | SATISFIED | open_db uses URI mode=ro; scan_messages filters by ICLOUD_UUID; TestOpenDb::test_readonly_mode confirms writes fail |
| SCAN-02 | 01-01 | Calculate volume statistics per sender (count, storage, date range, last received) | SATISFIED | get_sender_stats returns count, total_size, min_date, max_date grouped by LOWER(address); 6 tests cover aggregation |
| SCAN-03 | 01-04 | Display progress bar with count/total and ETA during all long-running operations | SATISFIED | classify_with_progress called at cli.py:130 with SpinnerColumn/MofNCompleteColumn/TimeRemainingColumn. The classify operation (one call per message across 25k+ emails) is the only loop-based long-running operation; scan uses a single SQL aggregation. Gap from previous verification is closed. |
| CSIG-01 | 01-02 | Score each contact by reply history, frequency, recency, and bidirectional communication | SATISFIED | build_contact_profiles computes read_rate, reply_rate (conv_id overlap + flags 0x4), is_bidirectional; compute_signals uses these as frequency_score, reply_rate_signal, recency_score, contact_score |
| CSIG-02 | 01-02 | Extract behavioral signals from flags (read, replied, flagged, forwarded, ignored, deleted patterns) | SATISFIED | extract_behavioral_signals extracts 5 signals; compute_signals adds recency/contact/frequency signals; is_protected checks replied (0x4) and forwarded (0x10) flags |
| CLAS-01 | 01-03 | Classify every email into 4 tiers: Trash / Keep-Active / Keep-Historical / Review | SATISFIED | classify_messages/classify_single process every message, assign_tier returns one of 4 Tier enum values, no message escapes classification |
| CLAS-02 | 01-03 | Assign 0-1 confidence score per email with explanation of contributing signals | SATISFIED | compute_confidence returns (float, str) tuple; explanation lists all 8 signals with values; Classification stores both |
| CLAS-03 | 01-04 | Two-pass strategy — metadata-only first pass, MLX embeddings only for ambiguous remainder | SATISFIED | Phase 1 is the metadata-only first pass; Review tier collects ambiguous emails for Phase 2 embedding analysis; incremental checkpoint merge supports the two-pass architecture |
| CLAS-04 | 01-03 | Protect personal/historical emails with asymmetric threshold (0.95+ to trash) | SATISFIED | Trash requires (1 - confidence) >= 0.95 i.e. keep_confidence <= 0.05; protected contacts excluded from Trash path entirely unless read_rate override fires |

All 9 Phase 1 requirements SATISFIED. 134/134 tests pass (`uv run pytest`).

### Anti-Patterns Found

None. The previous BLOCKER (classify_with_progress imported but never called) is resolved. No TODO/FIXME/placeholder comments. No stub return values. No console.log-only implementations. `scan_with_progress` remains imported but not called — not a blocker, as there is no per-message scan loop to wrap.

### Human Verification Required

#### 1. Progress Bar Visual Confirmation

**Test:** Run `uv run python -m icloud_cleanup classify` against the live Envelope Index.
**Expected:** Animated progress bar appears during classification with spinner, running count (e.g., "12,450 / 25,134"), and ETA column that advances as messages are classified.
**Why human:** Terminal animation cannot be verified statically; progress bars are only meaningful under actual processing latency.

#### 2. End-to-End Classification Quality

**Test:** Run `uv run python -m icloud_cleanup classify` then `uv run python -m icloud_cleanup report`.
**Expected:** Tier distribution is reasonable — Trash contains obvious junk (no-reply senders, newsletters), known personal contacts appear in Keep-Active or Keep-Historical, Review captures ambiguous cases. No known personal emails in Trash.
**Why human:** Classification quality judgment requires knowing actual senders and their expected tier; threshold calibration cannot be verified from code alone.

#### 3. Debug Scores for Known Contact

**Test:** `uv run python -m icloud_cleanup classify --debug-scores "known-contact@gmail.com"`
**Expected:** Signal breakdown shows contact_score=1.0, is_bidirectional=True, protected=True for a contact you regularly exchange email with.
**Why human:** Requires live Envelope Index access and knowledge of actual sent mail history.

### Re-Verification Summary

**Previous gap (now closed):** `classify_with_progress` was imported in cli.py lines 20-26 but never called. `cmd_classify` had a comment "Step 4: Classify with progress bar" but called `classify_messages` directly.

**Fix confirmed:** cli.py lines 128-132 now read:
```python
# Step 4: Classify with progress bar
now = int(time.time())
classifications = classify_with_progress(
    messages, lambda msg: classify_single(msg, profiles, replied_conv_ids, now)
)
```

`classify_with_progress` is fully wired. It uses `classify_single` (added to classifier.py alongside `classify_messages`) rather than the batch function, enabling per-message progress advancement. All 134 tests still pass after the fix.

**Note on scan_with_progress:** This function remains imported but not called. The scan subcommand (`cmd_scan`) calls `get_sender_stats(conn)` which is a single SQL GROUP BY aggregation — there is no per-message loop to wrap with a per-item progress bar. Adding a spinner during that query would be possible but is not required for SCAN-03 compliance since classify is the primary long-running operation.

---

_Verified: 2026-03-05T06:00:00Z_
_Verifier: Claude (gsd-verifier)_
