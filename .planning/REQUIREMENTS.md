# Requirements: iCloud Mail Cleanup v2

**Defined:** 2026-03-04
**Core Value:** Aggressively eliminate junk mail while guaranteeing zero false positives on personally meaningful emails

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Scanning

- [ ] **SCAN-01**: Scan Envelope Index SQLite DB read-only for user@icloud.com (alias user@me.com)
- [ ] **SCAN-02**: Calculate volume statistics per sender (count, storage, date range, last received)
- [ ] **SCAN-03**: Display progress bar with count/total and ETA during all long-running operations
- [ ] **SCAN-04**: Parse .emlx files from disk for email body content extraction

### Classification Signals

- [ ] **CSIG-01**: Score each contact by reply history, frequency, recency, and bidirectional communication
- [ ] **CSIG-02**: Extract behavioral signals from flags (read, replied, flagged, forwarded, ignored, deleted patterns)
- [ ] **CSIG-03**: Generate MLX embeddings from combined subject+body text using M1 Max GPU
- [ ] **CSIG-04**: Cluster emails semantically across senders (e.g., group all shipping notifications regardless of sender)

### Classification

- [ ] **CLAS-01**: Classify every email into 4 tiers: Trash / Keep-Active / Keep-Historical / Review
- [ ] **CLAS-02**: Assign 0-1 confidence score per email with explanation of contributing signals
- [ ] **CLAS-03**: Two-pass strategy — metadata-only first pass, MLX embeddings only for ambiguous remainder
- [ ] **CLAS-04**: Protect personal/historical emails (friends, old jobs, memories) with asymmetric threshold (0.95+ to trash)

### Review & Execution

- [ ] **EXEC-01**: Generate detailed cleanup report grouped by category with examples and confidence distributions
- [ ] **EXEC-02**: Interactive terminal walkthrough — category-by-category review with approve/reject per group
- [ ] **EXEC-03**: Reversible execution — move to Trash only, maintain action log with restore capability
- [ ] **EXEC-04**: Claude API fallback for ambiguous cases (metadata summaries only, never full email bodies)

## v2 Requirements

### Ongoing Filtering

- **FILT-01**: Automatic classification of new incoming emails
- **FILT-02**: Custom mail rules based on classification signals
- **FILT-03**: Periodic scheduled cleanup runs

### Enhanced Features

- **ENHC-01**: Unsubscribe detection and flagging (List-Unsubscribe header)
- **ENHC-02**: Multi-account support (additional iCloud/email accounts)
- **ENHC-03**: Semantic clustering visualization (interactive exploration of email themes)

## Out of Scope

| Feature | Reason |
|-|-|
| Apple Mail category labels as input | Unreliable — the problem we're solving |
| IMAP direct connection | Local DB is faster, safer, sufficient |
| Auto-unsubscribe execution | Privacy/trust risk, phishing vectors in unsubscribe links |
| GUI / web interface | CLI tool, Rich terminal UI is sufficient |
| Permanent deletion | Irreversible — Trash only, 30-day recovery window |
| Full email bodies to cloud API | Privacy violation — metadata summaries only for ambiguous cases |
| Real-time daemon mode | Not needed for one-time cleanup tool |
| Data selling / analytics | Contradicts privacy-first positioning |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-|-|-|
| SCAN-01 | Phase 1 | Pending |
| SCAN-02 | Phase 1 | Pending |
| SCAN-03 | Phase 1 | Pending |
| SCAN-04 | Phase 2 | Pending |
| CSIG-01 | Phase 1 | Pending |
| CSIG-02 | Phase 1 | Pending |
| CSIG-03 | Phase 2 | Pending |
| CSIG-04 | Phase 2 | Pending |
| CLAS-01 | Phase 1 | Pending |
| CLAS-02 | Phase 1 | Pending |
| CLAS-03 | Phase 1 | Pending |
| CLAS-04 | Phase 1 | Pending |
| EXEC-01 | Phase 3 | Pending |
| EXEC-02 | Phase 3 | Pending |
| EXEC-03 | Phase 3 | Pending |
| EXEC-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0

---
*Requirements defined: 2026-03-04*
*Last updated: 2026-03-04 after roadmap creation*
