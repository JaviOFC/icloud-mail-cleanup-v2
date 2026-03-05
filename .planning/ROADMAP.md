# Roadmap: iCloud Mail Cleanup v2

## Overview

Build an intelligent email classification pipeline in three phases: first, a metadata-only classifier that reads the Envelope Index and scores contacts/behavior to classify ~60% of emails; second, MLX GPU embeddings for content analysis on the ambiguous remainder; third, the interactive review and safe execution layer that turns classifications into approved deletions. Each phase delivers usable output before the next begins.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Scanning + Metadata Classification** - Read Envelope Index, score contacts and behavior, classify emails using metadata signals only
- [ ] **Phase 2: Content Analysis + Full Classification** - Parse .emlx bodies, generate MLX embeddings, cluster semantically, upgrade classification with content signals
- [ ] **Phase 3: Report, Review + Safe Execution** - Generate cleanup report, interactive terminal walkthrough, execute approved deletions with safety guarantees

## Phase Details

### Phase 1: Scanning + Metadata Classification
**Goal**: Users can scan their iCloud mailbox and get a working 4-tier classification of every email based on metadata signals alone
**Depends on**: Nothing (first phase)
**Requirements**: SCAN-01, SCAN-02, SCAN-03, CSIG-01, CSIG-02, CLAS-01, CLAS-02, CLAS-03, CLAS-04
**Success Criteria** (what must be TRUE):
  1. Running the tool scans the Envelope Index and displays sender volume statistics (count, size, date range) with a progress bar
  2. Every email is classified into one of 4 tiers (Trash / Keep-Active / Keep-Historical / Review) with a 0-1 confidence score and signal explanation
  3. Emails ever replied to, forwarded, or from known personal contacts are protected from Trash classification regardless of other signals
  4. The metadata-only first pass classifies a majority of emails with high confidence, deferring ambiguous emails to Review for Phase 2
  5. Classification output is saved as a JSON checkpoint artifact consumable by subsequent phases
**Plans**: TBD

Plans:
- [ ] 01-01: TBD
- [ ] 01-02: TBD
- [ ] 01-03: TBD

### Phase 2: Content Analysis + Full Classification
**Goal**: Users get significantly improved classification accuracy through on-device content analysis of ambiguous emails
**Depends on**: Phase 1
**Requirements**: SCAN-04, CSIG-03, CSIG-04
**Success Criteria** (what must be TRUE):
  1. The tool parses .emlx files from disk and extracts plain-text body content for emails that Phase 1 classified as Review/ambiguous
  2. MLX embeddings are generated on M1 Max GPU and emails are clustered semantically across senders (e.g., all shipping notifications grouped together regardless of sender)
  3. The fused classification (metadata + content signals) reclassifies previously-ambiguous emails, reducing the Review tier to a small fraction of total emails
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Report, Review + Safe Execution
**Goal**: Users can review classification results interactively and execute approved deletions safely with full reversibility
**Depends on**: Phase 2
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04
**Success Criteria** (what must be TRUE):
  1. A detailed cleanup report is generated showing categories, example emails, and confidence distributions in both JSON and human-readable format
  2. An interactive terminal walkthrough lets the user review and approve/reject each category group before any action is taken
  3. Approved deletions move emails to Trash only (never permanent delete), with a complete action log and restore capability
  4. For remaining low-confidence cases, users can opt in to Claude API analysis (metadata summaries only, never full bodies) to get final classifications
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Scanning + Metadata Classification | 0/3 | Not started | - |
| 2. Content Analysis + Full Classification | 0/2 | Not started | - |
| 3. Report, Review + Safe Execution | 0/2 | Not started | - |
