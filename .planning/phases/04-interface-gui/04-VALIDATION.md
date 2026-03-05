---
phase: 4
slug: interface-gui
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-05
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/test_tui.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_tui.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TUI-01 | 01 | 0 | App launches | unit | `pytest tests/test_tui.py::test_app_launches -x` | ❌ W0 | ⬜ pending |
| TUI-02 | 01 | 1 | Mode switching D/R/E/P | unit | `pytest tests/test_tui.py::test_mode_switching -x` | ❌ W0 | ⬜ pending |
| TUI-03 | 01 | 1 | Dashboard tier summary | unit | `pytest tests/test_tui.py::test_dashboard_tier_summary -x` | ❌ W0 | ⬜ pending |
| TUI-04 | 02 | 1 | Review cluster list loads | unit | `pytest tests/test_tui.py::test_review_cluster_list -x` | ❌ W0 | ⬜ pending |
| TUI-05 | 02 | 1 | Review detail updates | unit | `pytest tests/test_tui.py::test_review_detail_updates -x` | ❌ W0 | ⬜ pending |
| TUI-06 | 02 | 1 | Bulk select and approve | unit | `pytest tests/test_tui.py::test_bulk_approve -x` | ❌ W0 | ⬜ pending |
| TUI-07 | 03 | 2 | Execute screen progress | unit | `pytest tests/test_tui.py::test_execute_progress -x` | ❌ W0 | ⬜ pending |
| TUI-08 | 03 | 2 | Pipeline worker background | unit | `pytest tests/test_tui.py::test_pipeline_worker -x` | ❌ W0 | ⬜ pending |
| TUI-09 | 01 | 1 | Theme toggle | unit | `pytest tests/test_tui.py::test_theme_toggle -x` | ❌ W0 | ⬜ pending |
| TUI-10 | 01 | 1 | Help overlay | unit | `pytest tests/test_tui.py::test_help_overlay -x` | ❌ W0 | ⬜ pending |
| TUI-11 | 01 | 0 | CLI tui subcommand | unit | `pytest tests/test_tui.py::test_cli_tui_subcommand -x` | ❌ W0 | ⬜ pending |
| TUI-12 | 02 | 2 | Session interop | integration | `pytest tests/test_tui.py::test_session_interop -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tui.py` — all TUI test stubs
- [ ] `tests/conftest.py` update — checkpoint fixtures for TUI tests
- [ ] `pyproject.toml` update — add `pytest-asyncio` to dev deps, `asyncio_mode = "auto"`
- [ ] `pyproject.toml` update — add `textual[dev]` to dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual layout quality | Dashboard/Review split | Pixel-level layout needs human eyes | Launch TUI, verify panels render proportionally |
| Mouse click targets | Header tabs clickable | Textual Pilot simulates clicks but visual hit zones need verification | Click each tab, verify screen switch |
| Color theme consistency | TIER_COLORS across views | Color rendering varies by terminal | Check tier colors match in dashboard and review screens |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
