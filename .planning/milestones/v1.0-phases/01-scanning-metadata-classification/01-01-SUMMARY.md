---
phase: 01-scanning-metadata-classification
plan: 01
subsystem: database
tags: [sqlite3, dataclasses, envelope-index, tdd]

requires:
  - phase: none
    provides: first plan in project
provides:
  - Message, ContactProfile, Classification, SignalResult, Tier dataclasses
  - Scanner with open_db, scan_messages, get_sender_stats, get_sent_recipients, get_replied_conversation_ids
  - Mock Envelope Index conftest fixture with full schema
affects: [01-02, 01-03, 01-04]

tech-stack:
  added: [rich, pytest, sqlite3, dataclasses]
  patterns: [URI read-only DB access, TDD red-green-refactor, typed dataclass domain models]

key-files:
  created:
    - src/icloud_cleanup/models.py
    - src/icloud_cleanup/scanner.py
    - tests/conftest.py
    - tests/helpers.py
    - tests/test_models.py
    - tests/test_scanner.py
    - pyproject.toml
  modified:
    - src/icloud_cleanup/__init__.py

key-decisions:
  - "Extracted test helpers to tests/helpers.py since conftest.py functions are not directly importable by test modules"
  - "Used COALESCE for sender_address and subject to handle NULL foreign keys gracefully"

patterns-established:
  - "TDD with separate RED/GREEN commits for each task"
  - "Mock Envelope Index via in-memory SQLite with real schema in conftest.py"
  - "All scanner functions accept Connection (not Path) for testability"

requirements-completed: [SCAN-01, SCAN-02]

duration: 4min
completed: 2026-03-05
---

# Phase 1 Plan 01: Project Setup and Scanner Summary

**Typed domain models (5 dataclasses) and read-only Envelope Index scanner with bulk extraction, sender stats, sent recipient mapping, and conversation-based reply detection**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-05T03:59:39Z
- **Completed:** 2026-03-05T04:03:55Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Project initialized with uv, rich, pytest; all domain types defined as typed dataclasses
- Scanner module with 5 functions covering full DB access layer (open, scan, sender stats, sent recipients, replied conversations)
- 39 tests passing with TDD workflow (RED-GREEN for both tasks)

## Task Commits

Each task was committed atomically (TDD: test then implementation):

1. **Task 1: Project setup and domain models**
   - `ed68631` test(01-01): add failing tests for domain models and conftest fixtures
   - `680665a` feat(01-01): add domain models and project setup
2. **Task 2: Scanner module -- DB access and bulk extraction**
   - `10a2a1e` test(01-01): add failing tests for scanner module
   - `e440d72` feat(01-01): implement scanner module with DB access and bulk extraction

## Files Created/Modified
- `pyproject.toml` - Project config: icloud-cleanup, python >=3.11, rich dep, pytest config
- `src/icloud_cleanup/__init__.py` - Package init with version
- `src/icloud_cleanup/models.py` - Tier enum + Message, ContactProfile, SignalResult, Classification dataclasses
- `src/icloud_cleanup/scanner.py` - open_db, scan_messages, get_sender_stats, get_sent_recipients, get_replied_conversation_ids
- `tests/__init__.py` - Test package marker
- `tests/conftest.py` - db fixture with full Envelope Index schema, seed mailboxes/addresses/subjects
- `tests/helpers.py` - insert_message and insert_recipient helper functions
- `tests/test_models.py` - 15 tests for all dataclasses and conftest
- `tests/test_scanner.py` - 24 tests for all scanner functions

## Decisions Made
- Extracted test helpers to `tests/helpers.py` rather than keeping them in conftest.py -- pytest auto-loads conftest but it's not importable as a module by test files
- Used COALESCE in SQL for sender_address and subject to return empty string instead of NULL -- downstream code can rely on string type without None checks

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Conftest helpers not importable**
- **Found during:** Task 2 (writing test_scanner.py)
- **Issue:** `from conftest import insert_message` fails because pytest conftest.py is not a regular importable module
- **Fix:** Created `tests/helpers.py` with the helper functions, conftest re-exports them
- **Files modified:** tests/helpers.py (new), tests/conftest.py (simplified)
- **Verification:** All tests import and pass
- **Committed in:** `10a2a1e` (Task 2 RED commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minor structural change to test organization. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All domain models ready for 01-02 (contact reputation model)
- Scanner functions provide the data extraction layer that 01-02 and 01-03 build on
- Mock DB fixtures ready for all future test files

## Self-Check: PASSED

All 7 created files verified on disk. All 4 commit hashes verified in git log.

---
*Phase: 01-scanning-metadata-classification*
*Completed: 2026-03-05*
