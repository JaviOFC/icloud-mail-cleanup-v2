# Project Research Summary

**Project:** iCloud Mail Cleanup v2
**Domain:** On-device email classification and bulk cleanup pipeline (macOS, Apple Silicon)
**Researched:** 2026-03-04
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a local-first, privacy-preserving email classification tool built on Apple's own data structures (Envelope Index SQLite + .emlx files on disk). The validated approach is a five-layer pipeline: extract metadata from the Envelope Index read-only, run three parallel signal extractors (sender reputation, content embeddings, behavioral patterns), fuse scores into a 4-tier classification with confidence, present an interactive review report, then execute approved deletions via AppleScript. The v1 codebase (which scanned 25K emails) proves the SQLite access and AppleScript execution patterns. v2 adds MLX-accelerated content embeddings as the primary differentiator — no competing tool does full local content analysis at this depth.

The stack is mature for the core layer (stdlib sqlite3, pathlib, email, uv, Python 3.13) and early-stage for the ML layer (mlx-embeddings 0.0.5, which is functional but API-unstable). The recommended embedding model is `nomic-ai/modernbert-embed-base` (8K context, Matryoshka 256-dim dimensions), with `mlx-community/all-MiniLM-L6-v2-4bit` as a well-tested fallback. All classification happens on-device; Claude API is a last-resort, opt-in-only fallback for the lowest-confidence ~5% of emails and must never receive full email bodies.

The dominant risks are (1) false positive deletion destroying personally meaningful emails — mitigated by asymmetric confidence thresholds (0.95+ required to trash, 0.5+ to keep) and unconditional protection for any email ever replied to or forwarded; and (2) AppleScript reliability at scale — mitigated by small batch sizes (25-50), pre-execution manifests, and post-execution verification. A two-pass classification strategy (metadata-only fast pass classifies ~60% of emails, GPU embeddings only for the ambiguous remainder) is the right architectural call for both speed and safety.

## Key Findings

### Recommended Stack

The stack is almost entirely stdlib plus a handful of well-chosen libraries. `sqlite3` (stdlib, `?mode=ro` URI) for Envelope Index access — zero deps, proven safe while Mail.app runs. `emlx==1.0.4` (pinned exact — .emlx format is frozen since 2005) for file parsing. `beautifulsoup4` for HTML-to-plain-text. `mlx` + `mlx-embeddings>=0.0.5` for GPU-accelerated embeddings on M1 Max 32-core GPU. `typer>=0.15.0` + `rich>=14.0` for CLI and terminal UI. `anthropic>=0.84.0` SDK for the optional Claude Haiku 4.5 API fallback via Batch API. `numpy` for vector math. No ORM, no vector database (25K * 256-dim = ~25MB, trivially in-memory), no NLP library (embeddings handle semantics directly).

**Core technologies:**
- `sqlite3` (stdlib): Envelope Index access — URI read-only mode (`?mode=ro`) proven safe while Mail.app runs
- `emlx==1.0.4`: .emlx parsing — only library that handles Apple's bytecount prefix + plist suffix correctly
- `mlx` + `mlx-embeddings>=0.0.5`: GPU embeddings — Apple's own framework, unified memory, zero CPU-GPU copy overhead on M1 Max
- `nomic-ai/modernbert-embed-base`: Embedding model — 8K context, Matryoshka 256-dim, 2024-25 architecture; fallback to `mlx-community/all-MiniLM-L6-v2-4bit`
- `typer>=0.15.0` + `rich>=14.0`: CLI — type-hint-driven subcommands, Rich tables/progress bars/prompts, native integration
- `anthropic>=0.84.0`: Optional Claude API — Haiku 4.5 via Batch API (~$0.50/1M input tokens), opt-in only, subject+sender never full body; <$1 total at 5% of 25K emails

### Expected Features

**Must have (table stakes):**
- Sender-based grouping with volume stats (count, size, date range) — every competitor has this
- Dry run / preview mode before any execution — non-negotiable for trust
- Bulk operations with user approval gate — core value prop
- Progress reporting — 25K emails with GPU processing takes minutes; user needs feedback
- Reversible deletion (Trash only, never permanent delete) — table stakes safety net

**Should have (differentiators — the reasons to build this vs use an existing tool):**
- 100% local on-device processing — GoodByEmail is the only local competitor, but metadata-only; this adds full content analysis
- 4-tier classification with confidence scores and explanations — no competitor shows *why* an email was classified
- Historical/sentimental email protection — no competitor protects old personal emails regardless of engagement
- Contact reputation scoring (reply history, bidirectional communication, frequency, sent-mail cross-reference)
- Behavioral signal analysis (read, replied, flagged, time patterns from Envelope Index flags bitmap)
- Interactive terminal walkthrough with Rich UI (category-by-category review with examples and signal scores)
- Hybrid ML: MLX local + Claude API opt-in fallback for bottom 5% ambiguous cases

**Defer (v2+ / post-launch):**
- Unsubscribe detection: detect List-Unsubscribe header, surface URL to user, no auto-execution
- Semantic clustering visualization: interesting but not actionable
- Multi-account support: single iCloud account is the correct scope for this project

**Anti-features (explicitly do not build):**
- IMAP connection or server-side operations
- Permanent deletion (ever)
- Full email body forwarding to any cloud API
- Apple Intelligence categories as classification input (they're why this tool exists)
- Ongoing mail filtering / daemon mode

### Architecture Approach

Five-layer sequential pipeline where each layer writes a JSON checkpoint artifact that the next layer consumes. This enables independent testing, caching, and re-runs without re-embedding. Two-pass classification: fast metadata-only pass classifies ~60% of emails (known contacts, replied-to, obvious spam), GPU embeddings run only on the ambiguous ~5-10K remainder. Three signal extractors run in parallel: ContactScorer, ContentEmbedder, BehaviorAnalyzer. ScoreFusion combines with weighted linear combination (content=0.40, contact=0.35, behavior=0.25). Unknown/missing signals default to 0.5 neutral to push ambiguous emails to Review, never Trash.

**Major components:**
1. `EnvelopeReader` — read-only SQLite queries, produces `list[EmailRecord]` typed dataclasses with all metadata and flags
2. `EmlxExtractor` — parallel .emlx parsing (6 workers, ProcessPoolExecutor), path resolution from mailbox structure, body text extraction
3. `ContactScorer` + `BehaviorAnalyzer` + `ContentEmbedder` — three parallel signal extractors producing 0.0-1.0 floats per sender/message
4. `ScoreFusion` — weighted combination, 4-tier assignment (Trash/Active/Historical/Review), confidence from signal agreement
5. `ReportGenerator` + `InteractiveReview` — JSON+Markdown output, Rich terminal walkthrough with per-group approval
6. `SafeExecutor` — AppleScript batch mover (25-50 per batch), pre-execution manifest, post-batch verification, action log

### Critical Pitfalls

1. **False positive deletion of personal emails** — The highest-stakes failure. Any email ever replied to, forwarded, or sent to by Javi must be unconditionally protected regardless of all other signals. Trash threshold must be 0.95+ confidence. The v1 NOREPLY_PATTERNS approach (`hello@`, `team@`, `info@`) is dangerous — only `noreply@`, `no-reply@`, `do-not-reply@`, `mailer-daemon@`, `bounce@` are safe auto-indicators.

2. **Same-sender mixed content (transactional vs. marketing)** — `noreply@amazon.com` sends both marketing and order confirmations. Classify at message level, not sender-group level. Add unconditional safeguards for transactional keywords (`order confirmation`, `receipt`, `password reset`, `security alert`, `two-factor`).

3. **AppleScript fragility at scale** — AppleScript's Mail.app `id` property may not map to SQLite ROWID (undocumented). Validate empirically with 5 known messages before any batch operation. Use 25-50 message batches. Write pre-execution manifest (JSON of every message to be trashed) before touching anything. Verify counts after each batch.

4. **Envelope Index schema is undocumented and can change across macOS versions** — Run schema validation at startup (`PRAGMA table_info()` on all expected tables). Auto-detect iCloud account UUID from mailboxes table rather than hardcoding `XXXXXXXX-...`. Add retry logic with exponential backoff (1s/2s/4s) for `SQLITE_BUSY` errors.

5. **Short email subjects degrade embedding quality** — Subject lines alone produce low-quality vectors. Combine `From: {sender} | Subject: {subject} | {body_preview}` as single embedding input. Set minimum 20-character threshold below which embeddings are skipped and non-content signals drive the decision entirely.

## Implications for Roadmap

The FEATURES.md MVP recommendation, ARCHITECTURE.md build order, and PITFALLS.md phase warnings all converge on the same 4-phase structure. Each phase produces usable output before the next phase begins.

### Phase 1: Data Foundation and Metadata-Only Classification

**Rationale:** EnvelopeReader is the dependency for everything else. Schema validation and WAL-safe reads must be proven before building classifiers on top. Metadata-only classification (ContactScorer + BehaviorAnalyzer) delivers a working tool without any ML dependency, validates the core pipeline structure, and classifies ~60% of emails with high confidence. ARCHITECTURE.md build order confirms EnvelopeReader → BehaviorAnalyzer → ContactScorer as the natural dependency chain.

**Delivers:** Working CLI with `--scan` and `--report` modes. Volume statistics, sender grouping, contact reputation scoring, behavioral signal extraction, deterministic classification for the easy majority, JSON report output.

**Addresses:** All 5 table-stakes features (sender grouping, dry run, bulk ops, progress, reversibility)

**Avoids:** DB locking (schema validation, retry logic, read-only URI), hardcoded UUID (auto-detection from mailboxes table), false positives from noreply pattern lists (conservative patterns only), message-level vs. sender-level classification design

**Research flag:** Standard patterns — well-documented SQLite, Python dataclasses, uv project setup. Schema knowledge from v1 is directly reusable. Skip research-phase for planning.

### Phase 2: Content Analysis and MLX Embeddings

**Rationale:** Content embeddings are the core differentiator and the most technically uncertain component. mlx-embeddings is 0.0.5 and API-unstable. Building this after a working metadata classifier exists means there's a functional fallback if MLX integration has issues. Two-pass strategy means embeddings run only on the ~5-10K ambiguous emails from Phase 1, cutting GPU time by 50-75% and focusing the expensive work where it matters.

**Delivers:** EmlxExtractor (parallel .emlx parsing, path resolution), ContentEmbedder (MLX batch embeddings, semantic clustering), upgraded ScoreFusion combining all three signals, confidence scores based on signal agreement, improved coverage for the 40% of emails metadata can't confidently classify.

**Uses:** `mlx`, `mlx-embeddings>=0.0.5`, `emlx==1.0.4`, `beautifulsoup4`, `ProcessPoolExecutor` (6 workers proven from v1 scanner)

**Avoids:** Embedding short text (combined subject+sender+body input), model cold start (load once at session start), memory pressure (batch 256-512, checkpoint to disk), embedding all 25K emails (two-pass — ambiguous subset only)

**Research flag:** NEEDS deeper research during planning. mlx-embeddings API needs local validation before writing ContentEmbedder. ModernBERT compatibility with mlx-embeddings 0.0.5 needs testing. EMLX path resolution pattern (including numeric shard subdirectory) needs empirical verification. Flags bitmask bit positions need empirical validation.

### Phase 3: Report, Interactive Review, and Confidence Calibration

**Rationale:** Once classification quality is known, the UX layer can be built correctly. Interactive review is where safety happens — the user must see and approve before any execution. Confidence calibration (percentile-based thresholds, not raw similarity scores) and progressive disclosure (Trash groups first with examples, Review groups next, Keep summary last) are critical for the tool to be both trustworthy and fast to use.

**Delivers:** ReportGenerator (JSON + Markdown), InteractiveReview terminal walkthrough (Rich UI, category-by-category approval), bulk approval UX for obvious groups, confidence score calibration with random spot-check samples, statistics dashboard.

**Avoids:** Uncalibrated confidence presenting fake precision (display High/Medium/Low not percentages), review queue overload (progressive disclosure, bulk approval for high-confidence obvious groups), building UX before knowing actual classification output distributions

**Research flag:** Standard patterns — Rich library is well-documented. Confidence calibration approach (percentile-based thresholds) is well-understood. Skip research-phase.

### Phase 4: Safe Execution and Optional API Fallback

**Rationale:** Execution is the highest-risk phase — it actually moves emails. SafeExecutor must validate AppleScript ID mapping before any batch operation. The Claude API fallback is optional, opt-in, and goes last because Phases 1-3 may already classify everything confidently enough that API is rarely needed. The entire execution design is built around the assumption that a false positive (trashing a valuable email) is far more costly than a false negative (keeping a junk email).

**Delivers:** SafeExecutor (AppleScript batch mover, pre-execution manifest, post-batch verification, action log, undo/restore script), optional Claude API fallback (`--enable-api` flag, subject+sender-only payloads, Haiku 4.5 via Batch API, full audit log).

**Avoids:** AppleScript ID mapping errors (empirical validation first with 5 known messages), wrong message targeting (pre-execution manifest), half-complete batches (verify between each 25-50 message batch), privacy violation (opt-in only, no full body to API, audit every API call)

**Research flag:** AppleScript `message id` to SQLite ROWID mapping needs empirical validation during Phase 4 planning — this is the single most fragile integration point and it's undocumented. Claude Batch API integration is standard — skip research.

### Phase Ordering Rationale

- Foundation first: EnvelopeReader is a dependency for all other components; schema validation must be proven before any classifier runs on top of it
- Metadata before ML: a working metadata-only classifier is the fallback if MLX has issues and provides immediate value; validating the pipeline structure before adding GPU complexity is lower risk
- ML before UX: interactive review is only useful once classification quality is known; building UX around uncertain outputs wastes iteration cycles
- UX before execution: never allow execution without a review layer — this ordering makes data loss impossible until Phase 4 is explicitly enabled
- API fallback last: optional, privacy-sensitive, and the classification pipeline may handle everything well enough without it

### Research Flags

Phases needing deeper research during planning:
- **Phase 2:** mlx-embeddings 0.0.5 API shape (verify `load()`, `encode()`, output format against installed version), ModernBERT + mlx-embeddings compatibility, EMLX shard subdirectory path pattern on Sequoia, flags bitmask empirical validation
- **Phase 4:** AppleScript `message id` ↔ SQLite ROWID mapping — undocumented, must test empirically with current Mail.app version before writing any execution code

Phases with standard patterns (skip research-phase):
- **Phase 1:** SQLite read-only patterns, Python dataclasses pipeline, uv project setup — all well-documented with v1 precedent
- **Phase 3:** Rich terminal UI, confidence calibration with percentile thresholds — well-documented
- **Phase 4 (API part):** Anthropic SDK Batch API — standard, stable, well-documented

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack (core) | HIGH | sqlite3 + stdlib + typer + rich are mature and proven. emlx format is frozen since 2005. |
| Stack (ML layer) | MEDIUM | mlx-embeddings 0.0.5 is early-stage. ModernBERT model compatibility not yet locally tested. Wrap in adapter layer. |
| Features | HIGH | Competitive landscape well-researched. v1 direct experience informs decisions. Feature set is well-defined and scoped. |
| Architecture | HIGH | Five-layer pipeline is textbook for batch classification. Two-pass strategy is well-justified by scale math. Build order matches dependency graph exactly. |
| Pitfalls (data access) | HIGH | v1 validated Envelope Index patterns directly. WAL mode behavior, read-only access, schema quirks are known quantities. |
| Pitfalls (classification) | MEDIUM | False positive thresholds and signal weights need empirical validation with labeled test set. Asymmetric cost design is correct direction. |
| Pitfalls (execution) | LOW | AppleScript message ID mapping is undocumented and must be validated empirically. This is the one unknown that could cause silent data corruption. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **mlx-embeddings API shape:** The `model.encode()` call shape in STACK.md is inferred from README, not tested locally. First action in Phase 2: `uv add mlx-embeddings && python -c "from mlx_embeddings.utils import load; help(load)"`.
- **ModernBERT + mlx-embeddings compatibility:** Not yet tested locally. Test on Phase 2 day 1. If loading fails, fall back to `mlx-community/all-MiniLM-L6-v2-4bit` which is confirmed MLX-compatible.
- **AppleScript `id` ↔ ROWID mapping:** Must be validated empirically before any SafeExecutor code is written. Diagnostic: query 5 known messages by ROWID, find them via AppleScript, verify subject/sender match.
- **EMLX path structure with numeric shard subdirectories:** Full path pattern including shard dirs is not confirmed against Sequoia's actual layout. First action in EmlxExtractor build: directory walk + spot-check against known message IDs.
- **Flags bitmask bit positions:** `read`, `replied`, `flagged`, `forwarded` bit positions are undocumented. Empirical test: mark test emails in Mail.app and observe which bits change in the database.
- **Empirical .emlx file coverage:** Unknown what fraction of 25K Envelope Index records have corresponding .emlx files cached locally (Mail.app downloads lazily). This determines realistic content analysis coverage. Must measure at Phase 2 start.

## Sources

### Primary (HIGH confidence)
- v1 codebase at `~/claude_code_projects/icloud-mail-cleanup/` — Envelope Index schema, query patterns, WAL-safe read-only access, ICLOUD_UUID, AppleScript execution patterns
- [MLX documentation](https://ml-explore.github.io/mlx/build/html/index.html) — framework docs, Python 3.13 compatibility verified
- [mlx-embeddings GitHub (Blaizzy)](https://github.com/Blaizzy/mlx-embeddings) — model support list, batch processing API
- [emlx GitHub (mikez)](https://github.com/mikez/emlx) — .emlx parser source, format stability confirmed
- [Anthropic Batch API docs](https://www.anthropic.com/news/message-batches-api) — 50% discount, 10K query limit, pricing
- [SQLite WAL Mode](https://sqlite.org/wal.html) — read-only connection behavior in WAL mode
- [Rich 14.x docs](https://rich.readthedocs.io/en/stable/) — terminal formatting API
- [Typer docs](https://typer.tiangolo.com/) — CLI framework

### Secondary (MEDIUM confidence)
- [nomic-ai/modernbert-embed-base (HuggingFace)](https://huggingface.co/nomic-ai/modernbert-embed-base) — model specs, Matryoshka dimensions (not yet tested locally with mlx-embeddings)
- [Mail.app Database Schema](https://labs.wordtothewise.com/mailapp/) — undocumented schema reference (community-maintained, validated against v1 experience)
- [Deep Dive Into Filing Mail via AppleScript](https://msgfiler.wordpress.com/2024/02/12/a-deep-dive-into-filing-mail-messages-using-applescript/) — message ID mapping analysis
- [Batch Moving Emails in Apple Mail (MacScripter)](https://www.macscripter.net/t/batch-moving-emails-in-apple-mail/73203) — AppleScript batch performance issues

### Tertiary (LOW confidence — validate during implementation)
- AppleScript `message id` ↔ SQLite ROWID correspondence — inferred from community posts, not Apple-documented
- mlx-embeddings `.encode()` API call signature — described in GitHub README but 0.0.5 may shift
- EMLX numeric shard subdirectory pattern — described in forensic analysis sources, not Apple-official

---
*Research completed: 2026-03-04*
*Ready for roadmap: yes*
