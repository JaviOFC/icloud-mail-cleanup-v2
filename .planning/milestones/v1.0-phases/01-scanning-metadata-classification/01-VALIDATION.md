---
phase: 1
slug: scanning-metadata-classification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-04
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | SCAN-01 | unit | `uv run pytest tests/test_scanner.py::test_open_db_readonly -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | SCAN-02 | unit | `uv run pytest tests/test_scanner.py::test_sender_stats -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | SCAN-03 | manual-only | Manual: visually confirm progress bar | N/A | ⬜ pending |
| 01-02-01 | 02 | 1 | CSIG-01 | unit | `uv run pytest tests/test_contacts.py::test_contact_scoring -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | CSIG-02 | unit | `uv run pytest tests/test_contacts.py::test_behavioral_signals -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | CLAS-01 | unit | `uv run pytest tests/test_classifier.py::test_tier_assignment -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | CLAS-02 | unit | `uv run pytest tests/test_classifier.py::test_confidence_score -x` | ❌ W0 | ⬜ pending |
| 01-03-03 | 03 | 2 | CLAS-03 | unit | `uv run pytest tests/test_classifier.py::test_review_deferral -x` | ❌ W0 | ⬜ pending |
| 01-03-04 | 03 | 2 | CLAS-04 | unit | `uv run pytest tests/test_classifier.py::test_protection_rules -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (mock DB connection, sample messages, sample contacts)
- [ ] `tests/test_scanner.py` — stubs for SCAN-01, SCAN-02
- [ ] `tests/test_contacts.py` — stubs for CSIG-01, CSIG-02
- [ ] `tests/test_classifier.py` — stubs for CLAS-01, CLAS-02, CLAS-03, CLAS-04
- [ ] `pyproject.toml` — pytest config section
- [ ] Framework install: `uv add --dev pytest`

**Testing strategy:** Tests use an in-memory SQLite database with a fixture that creates the Envelope Index schema and populates it with controlled test data. Do NOT test against the live Envelope Index.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Progress bar renders during scan | SCAN-03 | Visual/terminal output | Run `uv run python -m icloud_cleanup.cli scan` and confirm animated progress bar with ETA |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
