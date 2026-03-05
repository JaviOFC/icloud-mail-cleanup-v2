---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: "Review, Execute, and Pipeline screens complete. All 4 core screens built."
stopped_at: Completed 04-02-PLAN.md and 04-03-PLAN.md (wave 2)
last_updated: "2026-03-05T20:41:29Z"
last_activity: "2026-03-05 - Completed wave 2: plans 04-02 and 04-03"
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 14
  completed_plans: 14
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-04)

**Core value:** Aggressively eliminate junk mail while guaranteeing zero false positives on personally meaningful emails
**Current focus:** Phase 4 (Interface & GUI) in progress -- building Textual TUI.

## Current Position

Phase: 4 of 4 (Interface & GUI)
Plan: 3 of 4 in current phase -- Review, Execute & Pipeline screens complete
Status: Review screen (cluster list/detail split, multi-select, propagation tab, auto-triage, API fallback), Execute screen (dry-run default, live progress), and Pipeline screen (scan/classify/analyze worker) implemented.
Last activity: 2026-03-05 - Completed wave 2: plans 04-02 and 04-03

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 14
- Average duration: 4min
- Total execution time: 0.95 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 4 | 12min | 3min |
| 2 | 3 | 15min | 5min |
| 3 | 3 | 16min | 5min |
| 4 | 3 | 22min | 7min |

**Recent Trend:**
- Last 5 plans: 03-02 (5min), 03-03 (5min), 04-01 (6min), 04-02 (9min), 04-03 (7min)
- Trend: Steady

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 3-phase coarse structure -- metadata classification first, MLX content second, review+execution third
- [Roadmap]: CLAS-04 (personal email protection) placed in Phase 1 -- safety must be enforced from the first classification pass
- [Roadmap]: Phases 3+4 from research merged into single Phase 3 -- review and execution are one user workflow at coarse granularity
- [01-01]: Test helpers extracted to tests/helpers.py -- conftest.py not importable as regular module by test files
- [01-01]: COALESCE for sender_address/subject in scan query -- downstream code gets strings not None
- [01-02]: Reply rate combines conversation_id overlap AND flags bit 2 -- uses both detection methods for fuller coverage
- [01-02]: Protection override at strict <5% read rate (not <=) -- 5% itself keeps protection
- [01-02]: Empty sender addresses filtered from profile building -- avoids phantom profiles from NULL FK rows
- [01-03]: Confidence = keep-worthiness (higher = more worth keeping), Trash requires confidence <= 0.05
- [01-03]: Recency decay lambda=0.003 (~231-day half-life) -- acceptable approximation of "~1 year"
- [01-03]: Frequency score = read_rate * min(1.0, received_count/20) -- normalizes volume against engagement
- [01-03]: Unknown senders get zeroed-out default ContactProfile -- ensures every message gets classified
- [01-04]: No new decisions -- plan executed as written, wiring existing modules into CLI
- [02-01]: Truncated .emlx files with parseable content not rejected -- Python email module intentionally lenient
- [02-01]: Optional dataclass fields (default None) for backward-compatible Classification extension
- [02-02]: Guard HDBSCAN against n_samples < min_samples with early return of all-noise labels
- [02-02]: Catch TfidfVectorizer ValueError when max_df prunes all terms (identical-text clusters)
- [02-03]: Trash promotion gated on content_score > 0.65 — neutral noise must not override metadata trash
- [02-03]: HDBSCAN tuned to min_cluster_size=25, min_samples=10 for ~30 clusters on 24k emails
- [02-03]: Module-level worker functions with local imports for ProcessPoolExecutor compatibility
- [02-03]: mlx-embeddings TokenizerWrapper needs inner tokenizer access via _tokenizer attribute
- [03-01]: Confidence sparkline uses unicode block chars (no rich-sparklines dep)
- [03-01]: Auto-triage thresholds: cluster unanimity > 0.85, sender consistency > 0.80
- [03-01]: Protected emails block trash resolution for entire cluster/sender group
- [03-01]: Noise clusters (id=None/-1) always skipped in cluster unanimity pass
- [03-02]: AppleScript uses 'set mailbox of' (never 'delete') for predictable IMAP trash moves
- [03-02]: Action log stores both message_id and rowid_in_db for audit completeness
- [03-02]: API payloads use conservative 200/50 token averages for cost estimation
- [03-02]: Metadata-only API payloads -- no body text ever sent to Claude API
- [03-03]: Auto-approve threshold at 0.98 confidence for trash items (not 0.95)
- [03-03]: Common email domains excluded from domain propagation (18 providers)
- [03-03]: Propagation uses two strategies: exact domain match and subdomain match
- [03-03]: Review session saved after every cluster decision for crash-safe resumability
- [03-03]: CLI execute uses separate --execute flag for dry-run-by-default safety
- [04-01]: Textual 1.0.0 installed (not 8.x as research assumed -- 1.0.0 is the actual latest stable release)
- [04-01]: MODES uses class references (callables) instead of string names for reliable screen resolution
- [04-01]: Dashboard polls for async data via set_timer(0.3) instead of reactive attributes for simplicity
- [04-01]: Lazy import of icloud_cleanup.tui in CLI avoids textual import overhead for non-TUI commands
- [04-02]: app.call_from_thread (not self.call_from_thread) in @work methods -- Textual 1.0 has call_from_thread on App only
- [04-02]: Cluster labels disambiguated with tier suffix when duplicated across tiers
- [04-02]: All domain module imports at top level for test mockability
- [04-02]: PropagationTabWidget selects all on bulk-approve if none explicitly selected
- [04-03]: app.call_from_thread() used for thread-safe widget updates (Screen lacks this method in Textual 1.0.0)
- [04-03]: Pipeline step 3 (MLX content analysis) degrades gracefully if dependencies unavailable
- [04-03]: Execute screen chunks to batch_size=100 for progress granularity

### Roadmap Evolution

- Phase 4 added: Interface & GUI

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: mlx-embeddings 0.0.5 API is unstable -- needs local validation before writing ContentEmbedder
- [Phase 2]: ModernBERT compatibility with mlx-embeddings untested -- MiniLM fallback available
- [Phase 3]: ~~AppleScript message ID to SQLite ROWID mapping is undocumented~~ RESOLVED: ROWID == AppleScript `id` property (confirmed in 03-RESEARCH.md)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | scan project and update readme | 2026-03-05 | 6c0d66b | [1-scan-project-and-update-readme](./quick/1-scan-project-and-update-readme/) |

## Session Continuity

Last session: 2026-03-05T20:41:29Z
Stopped at: Completed wave 2 (04-02 and 04-03)
Resume file: .planning/phases/04-interface-gui/04-03-SUMMARY.md
