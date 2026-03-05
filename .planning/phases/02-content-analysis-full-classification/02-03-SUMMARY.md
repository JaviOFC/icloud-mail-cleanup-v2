---
phase: 02-content-analysis-full-classification
plan: 03
subsystem: fused-classification-pipeline
tags: [fused-scoring, reclassification, cli-analyze, progress-bars, multiprocessing, rich]

requires:
  - phase: 02-content-analysis-full-classification
    provides: embedder.py, clusterer.py, emlx_parser.py
provides:
  - Fused classification engine blending metadata (60%) + content (40%) scores
  - CLI `analyze` subcommand orchestrating full Phase 2 pipeline
  - Tier transition rules (Keep locked, Trash gated promotion, Review flexible)
  - Parallel body parsing with ProcessPoolExecutor
affects: [03-review-execution]

tech-stack:
  added: []
  patterns: [fused weighted scoring, tier-locked reclassification, ProcessPoolExecutor for I/O-bound parsing, Rich progress bars per pipeline stage]

key-files:
  created: []
  modified:
    - src/icloud_cleanup/classifier.py
    - src/icloud_cleanup/cli.py
    - tests/test_classifier.py

key-decisions:
  - "Trash promotion gated on content_score > 0.65 — neutral noise (0.5) must not override metadata trash decision"
  - "HDBSCAN tuned to min_cluster_size=25, min_samples=10 for ~30 clusters on 24k emails (was 100/20 producing only 3)"
  - "Keep tiers NEVER demoted — content fields updated only"
  - "_extract_body must be module-level function for ProcessPoolExecutor pickling"
  - "Worker processes need local import of parse_emlx_body (separate Python processes)"

patterns-established:
  - "Module-level worker functions with local imports for multiprocessing compatibility"
  - "Fused scoring: metadata_weight * metadata_confidence + content_weight * content_score, clamped [0,1]"
  - "Reclassification tier rules: locked tiers, gated promotions, flexible middle tier"

requirements-completed: [SCAN-04, CSIG-03, CSIG-04]

duration: 8min
completed: 2026-03-05
---

# Phase 2 Plan 03: Fused Classification & Analyze CLI Summary

**Fused classification engine with tier transition rules, full pipeline CLI subcommand, and parallel body parsing**

## Performance

- **Duration:** ~8 min (excluding human-verify wait time)
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint)
- **Files modified:** 3
- **Commits:** 8 (2 TDD + 1 feature + 5 fixes/tuning)

## Accomplishments
- `fuse_classification` blends metadata confidence (60%) with content score (40%) into single fused confidence
- `reclassify_with_content` enforces tier transition rules: Keep never demoted, Trash promotion gated on content_score > 0.65, Review has full flexibility
- CLI `analyze` subcommand orchestrates 6-step pipeline: load checkpoint → parse bodies → embed → cluster → reclassify → save
- Rich progress bars for parsing, embedding, and reclassification stages
- 6-worker parallel body parsing via ProcessPoolExecutor
- GPU batch_size=256, HDBSCAN n_jobs=-1 for multi-core clustering

## Pipeline Results (Real Data)
- **24,565 emails** processed end-to-end
- **30 clusters** with meaningful labels (AmEx, social media, art, invoices, Live IT, etc.)
- **23.7% noise** (healthy range)
- Phase 1 → Phase 2 tier changes:
  - Trash: 2 → 855 (+853 identified via content)
  - Keep Active: 114 → 114 (locked)
  - Keep Historical: 18,399 → 18,566 (+167 promoted from review)
  - Review: 6,050 → 5,030 (-17% reduction)

## Task Commits

1. **Task 1: Fused classification engine with reclassification rules**
   - `74db9a3` (test) - Failing tests for fused classification
   - `ad18437` (feat) - Fused scoring + reclassification implementation

2. **Task 2: CLI analyze subcommand wiring full pipeline**
   - `648980f` (feat) - Full pipeline wired into `analyze` subcommand

3. **Task 3: Human-verify checkpoint** — APPROVED
   - `d4da053` (fix) - Charset sanitization, tokenizer API fix, verbose log noise
   - `cfaab57` (fix) - Embedding progress bar
   - `c3abe5a` (fix) - Clustering tuning + trash promotion gate
   - `bf91c83` (perf) - Parallel parsing, larger GPU batches, multi-core clustering
   - `c57d6f9` (fix) - Module-level _extract_body for multiprocessing pickling

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Malformed charset in .emlx headers**
- **Issue:** `LookupError: unknown encoding: "utf-8"\n    content-transfer-encoding:7bit"` — multiline headers leaking into charset string
- **Fix:** Added `_safe_decode()` helper in emlx_parser.py that sanitizes charset strings
- **Committed in:** d4da053

**2. [Rule 1 - Bug] mlx-embeddings TokenizerWrapper API mismatch**
- **Issue:** `AttributeError: TokenizersBackend has no attribute batch_encode_plus`
- **Fix:** Access `tokenizer._tokenizer` (inner HF tokenizer) with `return_tensors="np"`, convert to MLX via `mx.array()`
- **Committed in:** d4da053

**3. [Rule 1 - Bug] Only 3 clusters instead of 20-50**
- **Issue:** HDBSCAN params too conservative (min_cluster_size=100, min_samples=20) for 24k emails
- **Fix:** Tuned to min_cluster_size=25, min_samples=10 → 30 clusters
- **Committed in:** c3abe5a

**4. [Rule 1 - Bug] Trash→Review promotion too aggressive (4,800 emails)**
- **Issue:** Neutral content_score=0.5 from noise clusters pushed borderline trash above threshold (0.20*0.6 + 0.5*0.4 = 0.32 > 0.30)
- **Fix:** Gated trash promotion on content_score > 0.65
- **Committed in:** c3abe5a

**5. [Rule 1 - Bug] Nested _extract_body unpicklable for ProcessPoolExecutor**
- **Issue:** `AttributeError: Can't get local object 'cmd_analyze.<locals>._extract_body'`
- **Fix:** Moved function to module level with local import of parse_emlx_body
- **Committed in:** c57d6f9, bf91c83

---

**Total deviations:** 5 auto-fixed (5 bugs discovered during real-data testing)
**Impact on plan:** All fixes necessary for production correctness. Tuning required for meaningful clustering on real email data.

## Files Modified
- `src/icloud_cleanup/classifier.py` - Added fuse_classification, reclassify_with_content, constants
- `src/icloud_cleanup/cli.py` - Added cmd_analyze with full pipeline, parallel parsing, progress bars
- `tests/test_classifier.py` - Added TestFusedClassification, TestReclassRules, trash+neutral test

## Next Phase Readiness
- Updated checkpoint at `~/.icloud-cleanup/checkpoint.jsonl` with fused classifications
- All content fields populated (content_score, cluster_id, cluster_label, content_source)
- Phase 3 can read checkpoint and present review UI with full context

## Self-Check: PASSED

- All modified files exist on disk
- All 8 commits verified in git log
- 231 tests passing (214 baseline + 17 new)
- Pipeline verified on real data with approved results

---
*Phase: 02-content-analysis-full-classification*
*Plan: 03*
*Completed: 2026-03-05*
