---
phase: 02-content-analysis-full-classification
plan: 01
subsystem: parsing
tags: [emlx, email-parsing, html-stripping, mlx-embeddings, scikit-learn, dataclass]

requires:
  - phase: 01-scanning-metadata-classification
    provides: Classification dataclass, checkpoint save/load, Message model with ROWID
provides:
  - EMLX parser module with build_emlx_lookup, parse_emlx_body, strip_html
  - Extended Classification dataclass with content_score, cluster_id, cluster_label, content_source
  - Phase 2 dependencies installed (mlx-embeddings, scikit-learn, numpy)
affects: [02-02-embeddings, 02-03-fused-classification]

tech-stack:
  added: [mlx-embeddings 0.0.5, scikit-learn 1.8.0, numpy 2.4.2, mlx 0.31.0]
  patterns: [emlx byte-count + RFC822 parsing, stdlib HTMLParser for tag stripping, optional dataclass fields for backward compat]

key-files:
  created:
    - src/icloud_cleanup/emlx_parser.py
    - tests/test_emlx_parser.py
  modified:
    - src/icloud_cleanup/models.py
    - src/icloud_cleanup/checkpoint.py
    - pyproject.toml

key-decisions:
  - "Truncated .emlx files with parseable content are not rejected -- Python email module is intentionally lenient"
  - "cp1252 smart quote test uses raw bytes instead of MIMEText helper due to codec roundtrip limitations"

patterns-established:
  - "EMLX parsing: read byte-count line, read that many bytes, parse with email.message_from_bytes"
  - "HTML stripping: stdlib HTMLParser subclass with script/style skip, regex fallback for malformed"
  - "Optional dataclass fields: use default=None for backward-compatible extension"

requirements-completed: [SCAN-04]

duration: 4min
completed: 2026-03-05
---

# Phase 2 Plan 01: EMLX Parser and Content Model Extension Summary

**EMLX body extraction pipeline with ROWID lookup, HTML stripping via stdlib, and Classification model extended with 4 optional content fields**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-05T06:41:20Z
- **Completed:** 2026-03-05T06:45:17Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- EMLX parser module with 3 public functions: build_emlx_lookup (ROWID-to-Path mapping), parse_emlx_body (text extraction), strip_html (tag removal)
- Classification dataclass extended with content_score, cluster_id, cluster_label, content_source -- all optional with None defaults for Phase 1 backward compatibility
- Checkpoint save/load updated to handle new optional fields seamlessly
- Phase 2 dependencies installed: mlx-embeddings 0.0.5, scikit-learn 1.8.0, numpy 2.4.2, mlx 0.31.0
- 29 new tests (3 model + 26 parser) bringing total from 158 to 187, all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies and extend Classification model**
   - `0c075a3` (test) - Failing tests for Classification content fields
   - `0c35acf` (feat) - Extend Classification, update checkpoint, install deps
2. **Task 2: EMLX parser -- lookup table, body extraction, HTML stripping**
   - `8e339bc` (test) - Failing tests for EMLX parser module
   - `0f32e08` (feat) - EMLX parser implementation with all tests passing

## Files Created/Modified
- `src/icloud_cleanup/emlx_parser.py` - EMLX discovery, body extraction, HTML stripping (3 public functions)
- `src/icloud_cleanup/models.py` - Classification extended with 4 optional content fields
- `src/icloud_cleanup/checkpoint.py` - Save/load updated for new optional fields
- `pyproject.toml` - Added mlx-embeddings, scikit-learn, numpy dependencies
- `tests/test_emlx_parser.py` - 26 tests: lookup, HTML stripping, body extraction, error handling
- `tests/test_models.py` - 3 new tests for Classification content fields

## Decisions Made
- Truncated .emlx files with parseable content are not rejected: Python's email.message_from_bytes is intentionally lenient and can extract partial content. Only truly corrupt files (binary garbage, missing byte count) return None.
- Windows-1252 charset test uses raw bytes instead of MIMEText helper due to codec roundtrip limitations in Python's email.mime module.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Windows-1252 test fixture: MIMEText helper couldn't roundtrip cp1252 smart quotes (\x93/\x94) through decode+re-encode. Fixed by constructing raw RFC822 bytes directly in the test.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- EMLX parser ready for Plan 02 (embeddings) to call build_emlx_lookup and parse_emlx_body
- Classification model ready for Plan 03 (fused classification) to populate content_score, cluster_id, cluster_label
- All Phase 2 dependencies installed and importable
- Blocker from STATE.md still applies: mlx-embeddings 0.0.5 API needs local validation in Plan 02

## Self-Check: PASSED

- All 4 key files exist on disk
- All 4 task commits verified in git log
- 187 tests passing (158 baseline + 29 new)

---
*Phase: 02-content-analysis-full-classification*
*Plan: 01*
*Completed: 2026-03-05*
