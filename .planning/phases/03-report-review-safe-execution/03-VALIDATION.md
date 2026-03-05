---
phase: 3
slug: report-review-safe-execution
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-05
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2+ |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | EXEC-01 | unit | `uv run pytest tests/test_report.py -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 0 | EXEC-02 | unit | `uv run pytest tests/test_review.py -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 0 | EXEC-02 | unit | `uv run pytest tests/test_auto_triage.py -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 0 | EXEC-02 | unit | `uv run pytest tests/test_propagation.py -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 0 | EXEC-03 | unit | `uv run pytest tests/test_executor.py -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 0 | EXEC-04 | unit | `uv run pytest tests/test_api_fallback.py -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 01 | 1 | EXEC-01 | unit | `uv run pytest tests/test_report.py -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 01 | 1 | EXEC-01 | unit | `uv run pytest tests/test_report.py::test_confidence_viz -x` | ❌ W0 | ⬜ pending |
| 03-03-01 | 02 | 1 | EXEC-02 | unit | `uv run pytest tests/test_review.py -x` | ❌ W0 | ⬜ pending |
| 03-03-02 | 02 | 1 | EXEC-02 | unit | `uv run pytest tests/test_auto_triage.py -x` | ❌ W0 | ⬜ pending |
| 03-03-03 | 02 | 1 | EXEC-02 | unit | `uv run pytest tests/test_propagation.py -x` | ❌ W0 | ⬜ pending |
| 03-04-01 | 03 | 2 | EXEC-03 | unit | `uv run pytest tests/test_executor.py::test_action_log -x` | ❌ W0 | ⬜ pending |
| 03-04-02 | 03 | 2 | EXEC-03 | unit | `uv run pytest tests/test_executor.py::test_applescript_generation -x` | ❌ W0 | ⬜ pending |
| 03-04-03 | 03 | 2 | EXEC-03 | unit | `uv run pytest tests/test_executor.py::test_dry_run -x` | ❌ W0 | ⬜ pending |
| 03-04-04 | 03 | 2 | EXEC-03 | unit | `uv run pytest tests/test_executor.py::test_batch_execution -x` | ❌ W0 | ⬜ pending |
| 03-05-01 | 04 | 2 | EXEC-04 | unit | `uv run pytest tests/test_api_fallback.py::test_payload -x` | ❌ W0 | ⬜ pending |
| 03-05-02 | 04 | 2 | EXEC-04 | unit | `uv run pytest tests/test_api_fallback.py::test_cost_estimation -x` | ❌ W0 | ⬜ pending |
| 03-05-03 | 04 | 2 | EXEC-04 | unit | `uv run pytest tests/test_api_fallback.py::test_result_integration -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_report.py` — stubs for EXEC-01 report generation + confidence viz
- [ ] `tests/test_review.py` — stubs for EXEC-02 review session persistence
- [ ] `tests/test_auto_triage.py` — stubs for EXEC-02 auto-triage resolution
- [ ] `tests/test_propagation.py` — stubs for EXEC-02 propagation suggestions
- [ ] `tests/test_executor.py` — stubs for EXEC-03 action log, AppleScript generation, dry-run, batch
- [ ] `tests/test_api_fallback.py` — stubs for EXEC-04 payload, cost estimation, result integration

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Interactive review flow (questionary prompts) | EXEC-02 | questionary requires real terminal for arrow-key navigation | Run `icloud-cleanup review`, navigate categories with arrow keys, approve/reject batches |
| Actual AppleScript execution against Mail.app | EXEC-03 | Requires Mail.app running with real iCloud account | Run `icloud-cleanup execute --dry-run` first, then `icloud-cleanup execute` on small batch (10 msgs) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
