# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-11
**Phases:** 4 | **Plans:** 15 | **Execution time:** 1.15 hours

### What Was Built
- 14-signal metadata classifier with contact reputation and protection enforcement
- MLX GPU embeddings + HDBSCAN semantic clustering for content analysis
- Interactive review (CLI questionary + web UI + Textual TUI) with auto-triage and propagation
- Batch AppleScript executor with dry-run safety, action logging, and feedback loop
- Web review UI with hover previews, bulk actions, and shift+click selection (bonus — became preferred interface)

### What Worked
- Coarse 4-phase structure kept momentum — each phase delivered usable output
- Two-pass classification (metadata first, ML second) avoided expensive embedding for obvious cases
- 14 signals with optional normalization — new signals fire only when informative, no dilution
- Placing protection logic in Phase 1 (CLAS-04) — safety enforced from day one
- GSD workflow velocity: 15 plans in 1.15 hours (~5 min average per plan)

### What Was Inefficient
- Phases 2 & 3 never got VERIFICATION.md — skipped during fast execution
- Nyquist validation scaffolded but never completed for any phase
- TUI (Phase 4) took longest (34 min) due to UX polish iterations and Textual 1.0 API gaps
- Web UI was added as post-milestone quick tasks rather than a planned phase — would have been cleaner as Phase 5

### Patterns Established
- Optional signal weights with auto-normalization (compute_confidence divides by total_weight)
- Feedback loop: Laplace-smoothed per-sender from SQLite, improves accuracy on re-runs
- Batch AppleScript: generate single script for N messages, execute once (~50-100x speedup)
- Single-file web UI pattern: no build step, FastAPI serves static HTML, API endpoints for data

### Key Lessons
1. **Always-on neutral signals dilute existing signals** — learned the hard way during signal expansion. Keep new signals optional with fire-only-when-informative semantics.
2. **Web UI beats TUI for review workflows** — the web UI with hover previews and bulk actions was more practical than the Textual TUI for a data-heavy review interface.
3. **AppleScript ROWID == `id` property** — undocumented but confirmed. No mapping layer needed.
4. **mlx-embeddings API is unstable** — needs version pinning and model fallback. TokenizerWrapper needs `._tokenizer` access.

### Cost Observations
- Model mix: ~70% sonnet (execution), ~20% haiku (subagents), ~10% opus (planning/review)
- Sessions: ~8-10 across 7 days
- Notable: Plan execution at 5 min average is very efficient for this complexity level

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Execution Time | Phases | Key Change |
|-|-|-|-|
| v1.0 | 1.15 hours | 4 | Established GSD workflow, coarse granularity |

### Cumulative Quality

| Milestone | Tests | LOC (src) | LOC (tests) |
|-|-|-|-|
| v1.0 | 464 | 8,021 | 7,329 |

### Top Lessons (Verified Across Milestones)

1. Optional signals with auto-normalization prevent weight dilution
2. Web UI preferred over TUI for data-heavy review workflows
