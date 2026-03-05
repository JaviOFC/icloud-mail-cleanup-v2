---
phase: 2
slug: content-analysis-full-classification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-05
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
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
| 02-01-01 | 01 | 0 | SCAN-04 | unit | `uv run pytest tests/test_emlx_parser.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 0 | CSIG-03 | unit | `uv run pytest tests/test_embedder.py -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 0 | CSIG-04 | unit | `uv run pytest tests/test_clusterer.py -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 0 | CSIG-04 | unit | `uv run pytest tests/test_classifier.py::TestFusedClassification -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 1 | SCAN-04 | unit | `uv run pytest tests/test_emlx_parser.py -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 1 | SCAN-04 | unit | `uv run pytest tests/test_emlx_parser.py::TestErrorHandling -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 1 | SCAN-04 | unit | `uv run pytest tests/test_emlx_parser.py::TestHtmlStripping -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 1 | SCAN-04 | unit | `uv run pytest tests/test_emlx_parser.py::TestLookupTable -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 2 | CSIG-03 | unit/integration | `uv run pytest tests/test_embedder.py -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 2 | CSIG-03 | unit | `uv run pytest tests/test_embedder.py::TestBatchEmbed -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 2 | CSIG-03 | unit | `uv run pytest tests/test_embedder.py::TestFallback -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 3 | CSIG-04 | integration | `uv run pytest tests/test_clusterer.py::TestClustering -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 3 | CSIG-04 | unit | `uv run pytest tests/test_clusterer.py::TestLabeling -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | XX | 3 | CSIG-04 | unit | `uv run pytest tests/test_classifier.py::TestReclassRules -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_emlx_parser.py` — stubs for SCAN-04 (parsing, lookup, HTML stripping, error handling)
- [ ] `tests/test_embedder.py` — stubs for CSIG-03 (embedding generation, batch, fallback)
- [ ] `tests/test_clusterer.py` — stubs for CSIG-04 (clustering, labeling)
- [ ] Extended `tests/test_classifier.py` — covers fused scoring and reclassification rules
- [ ] Dependencies installed: `uv add mlx-embeddings scikit-learn numpy`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GPU acceleration active | CSIG-03 | Requires M1 Max GPU hardware | Run embedding on 100 emails, check `mx.metal.is_available()` returns True and processing time < 5s |
| Cluster quality subjective | CSIG-04 | Human judgment on cluster label relevance | Inspect 10 random cluster labels, verify they describe the grouped emails meaningfully |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
