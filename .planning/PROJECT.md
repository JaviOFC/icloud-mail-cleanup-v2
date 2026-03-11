# iCloud Mail Cleanup v2

## What This Is

An intelligent iCloud email cleanup tool that replaces Apple Mail's unreliable categorization with a 14-signal classification system. Scans the local Envelope Index database and `.emlx` files, combines contact reputation, MLX GPU embeddings, HDBSCAN clustering, and behavioral patterns to classify emails into 4 tiers, then guides the user through interactive review (CLI, TUI, or web UI) with per-category approval and safe batch execution via AppleScript.

## Core Value

Aggressively eliminate junk mail while guaranteeing zero false positives on personally meaningful emails — old friendships, career history, memories. The email archive is a data asset, not clutter.

## Requirements

### Validated

- ✓ Scan local Envelope Index SQLite DB read-only — v1.0
- ✓ Build contact reputation scoring (known contacts, reply history, frequency) — v1.0
- ✓ Analyze email content using local MLX embeddings on M1 Max GPU — v1.0
- ✓ Detect behavioral signals (read status, replied, ignored, deleted patterns) — v1.0
- ✓ Classify every email into 4 tiers: Trash / Keep-Active / Keep-Historical / Review — v1.0
- ✓ Assign confidence scores to each classification decision — v1.0
- ✓ Generate detailed cleanup report grouped by category with examples — v1.0
- ✓ Interactive terminal walkthrough for reviewing and approving/rejecting categories — v1.0
- ✓ Use Claude API for ambiguous/low-confidence cases only (hybrid ML) — v1.0
- ✓ Execute approved deletions safely (trash, not permanent delete) — v1.0
- ✓ Protect personal/historical emails from any deletion — v1.0
- ✓ Full Textual TUI with Dashboard, Review, Execute, Pipeline screens — v1.0
- ✓ Web review UI with cluster browsing, hover previews, bulk actions — v1.0 (bonus)

### Active

(None — planning next milestone)

### Out of Scope

- Apple Mail category labels as classification input — the whole point is to not trust them
- IMAP direct connection — using local DB is faster, safer, and sufficient
- Ongoing filtering / mail rules — v2 feature
- Exporting emails for career intelligence engine — separate project
- Multi-account support — single iCloud account only
- Auto-unsubscribe execution — privacy/trust risk, phishing vectors

## Context

Shipped v1.0 with 8,021 LOC Python + 7,329 LOC tests.
Tech stack: Python 3.11, MLX, HDBSCAN, Rich, Textual, FastAPI (web UI), AppleScript.
Validated on 24,894 emails spanning back to 2011.
Successfully used to clean inbox — tool works end-to-end.

**Post-v1.0 observations:**
- Web UI (`review --web`) became the preferred review interface over both CLI and TUI
- 14-signal classifier with optional signal normalization works well
- Feedback loop (Laplace-smoothed per-sender) improves accuracy on re-runs
- Batch AppleScript execution ~50-100x faster than one-at-a-time

## Constraints

- **Data source**: Local Envelope Index SQLite DB + `.emlx` files on disk (read-only queries)
- **Privacy**: All classification happens on-device. Claude API used only for ambiguous cases with user opt-in.
- **Safety**: No permanent deletes — only move to Trash. User must approve every batch.
- **Stack**: Python 3.11+, MLX for embeddings, `uv` for package management
- **Single account**: user@icloud.com (alias user@me.com)

## Key Decisions

| Decision | Rationale | Outcome |
|-|-|-|
| Don't use Apple Mail categories | They're unreliable — miscategorize real emails, poor junk detection | ✓ Good — our classifier outperforms Apple's categories |
| Local Envelope Index over IMAP | Faster, offline, no risk of modifying server state, already synced | ✓ Good — instant access to 25k emails |
| Hybrid ML (local + API) | MLX for bulk triage keeps costs at zero, Claude API only for ambiguous edge cases | ✓ Good — API barely needed after content analysis |
| 4-tier classification | Trash/Active/Historical/Review captures user's mental model | ✓ Good — intuitive tier system |
| Reference-only from v1 | Schema knowledge reusable, fresh code for GSD rebuild | ✓ Good — cleaner architecture |
| Confidence = keep-worthiness | Higher confidence = more worth keeping. Trash requires <= 0.05 | ✓ Good — asymmetric threshold protects important emails |
| Optional signals with auto-normalization | New signals fire only when informative, weights auto-normalize | ✓ Good — avoids diluting existing signals |
| AppleScript 'set mailbox of' | Never 'delete' — predictable IMAP trash moves | ✓ Good — safe and reversible |
| Batch AppleScript execution | ~50-100x faster than one-at-a-time | ✓ Good — practical for large mailboxes |
| Web UI as review interface | FastAPI + single-file HTML, no build step | ✓ Good — became preferred interface |

---
*Last updated: 2026-03-11 after v1.0 milestone*
