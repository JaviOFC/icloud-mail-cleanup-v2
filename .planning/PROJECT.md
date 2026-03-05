# iCloud Mail Cleanup v2

## What This Is

An intelligent iCloud email cleanup tool that replaces Apple Mail's unreliable categorization with its own multi-signal classification system. Scans the local Envelope Index database and `.emlx` files, combines contact reputation, content analysis (MLX embeddings), and behavioral patterns (read/replied/ignored) to classify emails into 4 tiers, then guides the user through an interactive cleanup flow with a detailed report and per-category approval.

## Core Value

Aggressively eliminate junk mail while guaranteeing zero false positives on personally meaningful emails — old friendships, career history, memories. The email archive is a data asset, not clutter.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Scan local Envelope Index SQLite DB for user@icloud.com (alias user@me.com)
- [ ] Build contact reputation scoring (known contacts, reply history, frequency)
- [ ] Analyze email content using local MLX embeddings on M1 Max GPU
- [ ] Detect behavioral signals (read status, replied, ignored, deleted patterns)
- [ ] Classify every email into 4 tiers: Trash / Keep-Active / Keep-Historical / Review
- [ ] Assign confidence scores to each classification decision
- [ ] Generate detailed cleanup report grouped by category with examples and confidence tiers
- [ ] Interactive terminal walkthrough for reviewing and approving/rejecting categories
- [ ] Use Claude API for ambiguous/low-confidence cases only (hybrid ML)
- [ ] Execute approved deletions safely (trash, not permanent delete)
- [ ] Protect personal/historical emails — friends, old jobs, memories — from any deletion
- [ ] Reference existing Envelope Index schema knowledge but write all code from scratch

### Out of Scope

- Apple Mail category labels as classification input — the whole point is to not trust them
- IMAP direct connection — using local DB is faster, safer, and sufficient
- Ongoing filtering / mail rules — v2 feature
- Exporting emails for career intelligence engine — separate project handles that
- Multi-account support — single iCloud account only
- GUI / web interface — terminal-based tool

## Context

- **Existing tool:** `~/claude_code_projects/icloud-mail-cleanup/` has a working v1 that relies heavily on Apple Intelligence categories. This project is a GSD-driven rebuild to compare approaches.
- **Apple Mail problems:** Frequent miscategorization (real emails in "Updates"/"Promo"), poor junk filtering, no way to correct classifications. 36% of emails (9,124) were uncategorized entirely.
- **Email volume:** ~25,000+ emails in the iCloud account spanning back to 2011.
- **Career Intelligence Engine:** Separate project at `~/claude_code_projects/career-intelligence-engine/` uses email history for career pattern analysis. Historical emails are valuable — must not be deleted.
- **Hardware:** M1 Max with 32-core GPU, 16-core Neural Engine — ideal for local ML inference via MLX framework.
- **Envelope Index schema:** Known from v1 work. `messages.message_id = message_global_data.message_id` (not ROWID). `date_received` is Unix timestamp (no Apple epoch offset). Can reference v1's `lib/envelope_index.py` for schema knowledge.

## Constraints

- **Data source**: Local Envelope Index SQLite DB + `.emlx` files on disk (read-only queries)
- **Privacy**: All classification happens on-device. Claude API used only for ambiguous cases with user opt-in.
- **Safety**: No permanent deletes — only move to Trash. User must approve every batch.
- **Stack**: Python 3.11+, MLX for embeddings, `uv` for package management
- **Single account**: user@icloud.com (alias user@me.com)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Don't use Apple Mail categories | They're unreliable — miscategorize real emails, poor junk detection | — Pending |
| Local Envelope Index over IMAP | Faster, offline, no risk of modifying server state, already synced | — Pending |
| Hybrid ML (local + API) | MLX for bulk triage keeps costs at zero, Claude API only for ambiguous edge cases | — Pending |
| 4-tier classification | Trash/Active/Historical/Review captures user's mental model without oversimplifying | — Pending |
| Reference-only from v1 | Schema knowledge is reusable, but fresh code lets GSD prove its approach independently | — Pending |

---
*Last updated: 2026-03-04 after initialization*
