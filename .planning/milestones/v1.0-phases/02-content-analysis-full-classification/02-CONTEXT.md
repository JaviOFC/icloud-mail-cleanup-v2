# Phase 2: Content Analysis + Full Classification - Context

**Gathered:** 2026-03-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Parse .emlx email body files from disk, generate MLX embeddings on M1 Max GPU, cluster emails semantically across senders, and fuse content signals with Phase 1's metadata classification to reclassify ambiguous emails. No interactive review or execution — that's Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Content analysis scope
- Parse ALL ~25K emails' .emlx files, not just Review tier
- Generate embeddings for every email but only let content signals change classification for Review-tier and borderline cases
- Confident Trash/Keep from Phase 1 remain stable unless content strongly disagrees
- Extract plain text body only — no MIME header parsing (Envelope Index already has that metadata)
- For HTML-only emails: strip tags and normalize whitespace, no external HTML parsing library

### Cluster granularity
- Coarse clusters (~20-50 groups) — broad categories like "shipping notifications", "marketing emails", "account alerts"
- Auto-label clusters from content using heuristic keyword extraction (TF-IDF or similar), not Claude API
- No API dependency in Phase 2 — everything runs locally

### Reclassification rules
- **Trash → Keep/Review: YES** — content analysis can promote Trash-classified emails if content shows they're personal/important (safety net against metadata false positives)
- **Keep → Trash: NO** — Keep decisions from metadata are final. Aligns with "zero false positives" core value
- **Review → any tier: YES** — full flexibility for Review emails, this is the main target of Phase 2
- **Review can stay Review** — if content is still ambiguous, email stays in Review for Phase 3
- Single fused confidence score (metadata + content blended), not dual scores

### Missing .emlx handling
- Walk ~/Library/Mail/V10/ directory tree to build message-ID-to-filepath lookup table
- Missing .emlx files: fall back to subject-only embedding, flag as "subject_only" in output
- Corrupted/unparseable .emlx: same treatment as missing — subject-only fallback, log warning
- No blocking on parse failures — processing continues

### Claude's Discretion
- Clustering algorithm choice (DBSCAN, HDBSCAN, agglomerative, etc.)
- MLX embedding model selection (MiniLM, ModernBERT, etc.)
- Body length truncation limit (align with embedding model's context window)
- Exact weight blending between metadata and content signals for fused score
- Batch size and parallelization strategy for GPU embedding

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `models.py`: Message, Classification, Tier, SignalResult, ContactProfile dataclasses — Phase 2 extends these
- `classifier.py`: `compute_signals()`, `compute_confidence()`, `assign_tier()`, `classify_single()` — Phase 2 adds content signals to this pipeline
- `checkpoint.py`: JSONL save/load/merge — Phase 2 writes updated checkpoint after fused classification
- `scanner.py`: `open_db()`, `scan_messages()` — provides Message objects as input to content analysis
- `contacts.py`: `is_protected()`, `check_protection_override()` — protection rules carry through unchanged

### Established Patterns
- Read-only DB access via `file:{path}?mode=ro` URI
- Dataclass-based domain models with type hints
- Signal-based scoring (list of SignalResult with name/value/weight/explanation)
- Atomic file writes via tmp + os.replace
- `rich` library for progress display

### Integration Points
- Phase 1 checkpoint JSONL → Phase 2 reads existing classifications, adds content signals, writes updated checkpoint
- Message.message_id links DB records to .emlx files (via lookup table)
- Phase 2 output checkpoint consumed by Phase 3 (review + execution)
- New CLI subcommand needed (or extension of existing `classify` command)

</code_context>

<specifics>
## Specific Ideas

- M1 Max has 32-core GPU — MLX embeddings should saturate it for batch processing
- mlx-embeddings library exists but API may be unstable (noted in STATE.md blockers)
- ModernBERT compatibility with mlx-embeddings is untested — MiniLM is the fallback
- ~25K emails spanning back to 2011 — cluster distribution will be heavily skewed toward recent years

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-content-analysis-full-classification*
*Context gathered: 2026-03-05*
