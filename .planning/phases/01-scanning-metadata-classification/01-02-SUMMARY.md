---
phase: 01-scanning-metadata-classification
plan: 02
subsystem: contacts
tags: [contact-scoring, behavioral-signals, protection-logic, tdd]

requires:
  - phase: 01-scanning-metadata-classification
    provides: Message dataclass, scanner functions (get_sent_recipients, get_replied_conversation_ids, scan_messages), mock DB fixtures
provides:
  - build_contact_profiles -- ContactProfile for every unique sender with read/reply rates and bidirectional detection
  - is_protected -- 4-criteria protection logic (bidirectional, conversation overlap, replied flag, forwarded flag)
  - check_protection_override -- ratio-based override at <5% read rate for newsletter-replied-once pattern
  - extract_behavioral_signals -- 5 typed SignalResult objects per message
affects: [01-03, 01-04]

tech-stack:
  added: []
  patterns: [defaultdict grouping by lowercase address, combined reply detection (conversation overlap + flags bit), ratio-based protection override]

key-files:
  created:
    - src/icloud_cleanup/contacts.py
    - tests/test_contacts.py
  modified: []

key-decisions:
  - "Reply rate combines conversation_id overlap AND flags bit 2 -- uses both detection methods per research finding (6,841 replied conversations vs 2,884 replied flags)"
  - "Protection override threshold at exactly <5% read rate (strict less-than, not <=) -- 5% itself is considered engaged enough to keep protection"
  - "Empty sender addresses filtered out of profile building -- avoids creating phantom profiles for NULL sender rows"

patterns-established:
  - "ContactProfile built from Message list + sent_recipients dict + replied_conv_ids set (no DB dependency)"
  - "Protection is per-message (is_protected) while override is per-profile (check_protection_override)"
  - "_make_message() helper factory for unit tests needing Message objects without DB"

requirements-completed: [CSIG-01, CSIG-02]

duration: 2min
completed: 2026-03-05
---

# Phase 1 Plan 02: Contact Reputation Model Summary

**Contact reputation scoring with Sent-mailbox bidirectional detection, 4-criteria protection logic with ratio-based override, and 5 typed behavioral signals per message**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-05T04:06:43Z
- **Completed:** 2026-03-05T04:09:07Z
- **Tasks:** 1 (TDD: RED + GREEN commits)
- **Files modified:** 2

## Accomplishments
- Contact profiles computed for every sender with accurate read/reply/flagged metrics, bidirectional detection from Sent mailbox
- Reply detection combines conversation_id overlap (6,841 conversations) AND flags bit 2 (2,884 flags) for maximum coverage
- Protection logic implements all 4 criteria from CONTEXT.md locked decisions with ratio-based override at <5% read rate
- 30 new tests passing (69 total across project), including integration test with mock DB via scanner functions

## Task Commits

Each task was committed atomically (TDD: test then implementation):

1. **Task 1: Contact reputation model and protection logic**
   - `edca260` test(01-02): add failing tests for contact reputation model
   - `7433405` feat(01-02): implement contact reputation model and protection logic

## Files Created/Modified
- `src/icloud_cleanup/contacts.py` - Contact profiling (build_contact_profiles), protection logic (is_protected, check_protection_override), behavioral signal extraction (extract_behavioral_signals)
- `tests/test_contacts.py` - 30 tests covering all 4 exported functions with edge cases (case normalization, newsletter-replied-once pattern, real contact pattern)

## Decisions Made
- Reply rate combines both conversation_id overlap AND flags bit 2 -- the two detection methods capture different reply scenarios and together provide fuller coverage
- Protection override uses strict less-than 5% (not <=) -- a sender at exactly 5% read rate has enough engagement to warrant keeping protection
- Empty sender addresses (from NULL foreign keys) are filtered out during profile building to avoid phantom profiles
- _make_message() factory helper created for unit tests to avoid needing DB fixtures for pure-function tests

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Contact profiles and protection logic ready for 01-03 (metadata classifier)
- Classifier can call build_contact_profiles to get per-sender reputation, then is_protected + check_protection_override per message
- extract_behavioral_signals provides the signal inputs the classifier needs for weighted scoring
- All functions accept plain data (no DB dependency) making them easy to compose

---
*Phase: 01-scanning-metadata-classification*
*Completed: 2026-03-05*
