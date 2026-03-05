# Roadmap: iCloud Mail Cleanup v2

## Overview

Build an intelligent email classification pipeline in three phases: first, a metadata-only classifier that reads the Envelope Index and scores contacts/behavior to classify ~60% of emails; second, MLX GPU embeddings for content analysis on the ambiguous remainder; third, the interactive review and safe execution layer that turns classifications into approved deletions. Each phase delivers usable output before the next begins.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Scanning + Metadata Classification** - Read Envelope Index, score contacts and behavior, classify emails using metadata signals only
- [x] **Phase 2: Content Analysis + Full Classification** - Parse .emlx bodies, generate MLX embeddings, cluster semantically, upgrade classification with content signals
- [x] **Phase 3: Report, Review + Safe Execution** - Generate cleanup report, interactive terminal walkthrough, execute approved deletions with safety guarantees
- [ ] **Phase 4: Interface & GUI (TUI)** - Textual-based terminal application for interactive review, execution, and pipeline management

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
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md -- Project setup, domain models (Message/Contact/Classification), scanner module (DB access, bulk extraction, sender stats)
- [x] 01-02-PLAN.md -- Contact reputation model (Sent mailbox profiling, protection logic, behavioral signal extraction)
- [x] 01-03-PLAN.md -- Classification engine (8-signal weighted scoring, tier assignment, protection enforcement) + JSONL checkpoint persistence
- [x] 01-04-PLAN.md -- CLI wiring (scan/classify/report subcommands), rich progress bars, summary display, end-to-end verification

### Phase 2: Content Analysis + Full Classification
**Goal**: Users get significantly improved classification accuracy through on-device content analysis of ambiguous emails
**Depends on**: Phase 1
**Requirements**: SCAN-04, CSIG-03, CSIG-04
**Success Criteria** (what must be TRUE):
  1. The tool parses .emlx files from disk and extracts plain-text body content for emails that Phase 1 classified as Review/ambiguous
  2. MLX embeddings are generated on M1 Max GPU and emails are clustered semantically across senders (e.g., all shipping notifications grouped together regardless of sender)
  3. The fused classification (metadata + content signals) reclassifies previously-ambiguous emails, reducing the Review tier to a small fraction of total emails
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md -- Install dependencies, extend Classification model with content fields, EMLX parser (ROWID lookup, body extraction, HTML stripping)
- [x] 02-02-PLAN.md -- MLX batch embedding generator with model fallback, HDBSCAN clusterer with TF-IDF labeling and content score derivation
- [x] 02-03-PLAN.md -- Fused classification engine (metadata + content blending, reclassification rules), CLI analyze subcommand, end-to-end verification

### Phase 3: Report, Review + Safe Execution
**Goal**: Users can review classification results interactively and execute approved deletions safely with full reversibility
**Depends on**: Phase 2
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04
**Success Criteria** (what must be TRUE):
  1. A detailed cleanup report is generated showing categories, example emails, and confidence distributions in both JSON and human-readable format
  2. An interactive terminal walkthrough lets the user review and approve/reject each category group before any action is taken
  3. Approved deletions move emails to Trash only (never permanent delete), with a complete action log and restore capability
  4. For remaining low-confidence cases, users can opt in to Claude API analysis (metadata summaries only, never full bodies) to get final classifications
**Plans**: 4 plans

Plans:
- [x] 03-01-PLAN.md -- Report data builder (tier-first + cluster-detail views, JSON/Markdown/terminal formats) and auto-triage pre-review resolution engine
- [x] 03-02-PLAN.md -- AppleScript executor (ROWID-based trash moves, action log SQLite, dry-run, batch execution) and Claude API fallback (metadata payloads, cost estimation, batch API)
- [x] 03-03-PLAN.md -- Interactive review session (questionary prompts, resumable sessions, trash auto-approve) + propagation engine + CLI wiring (review, execute, enhanced report subcommands)
- [x] 03-04-PLAN.md -- End-to-end workflow verification checkpoint (report + review + dry-run execution on real data)

### Phase 4: Interface & GUI (TUI)
**Goal:** Users can interact with classification results, review clusters, execute deletions, and run the pipeline through a rich Textual-based terminal application
**Depends on:** Phase 3
**Requirements**: TUI-01, TUI-02, TUI-03, TUI-04, TUI-05, TUI-06, TUI-07, TUI-08, TUI-09, TUI-10, TUI-11, TUI-12
**Success Criteria** (what must be TRUE):
  1. Running `icloud_cleanup tui` launches a Textual app with Dashboard, Review, Execute, and Pipeline screens navigable via D/R/E/P keys
  2. The Dashboard shows tier summaries with sparklines, storage savings, and pipeline status
  3. The Review screen provides a two-column split (cluster list + detail) with multi-select bulk actions, auto-triage trigger, and propagation suggestions
  4. The Execute screen runs approved deletions with live progress (dry-run by default)
  5. The Pipeline screen can kick off scan/classify/analyze with progress bar and scrollable log
  6. Theme toggle, help overlay, and keyboard shortcuts work throughout
**Plans**: 4 plans

Plans:
- [x] 04-01-PLAN.md -- App shell, dependencies, Dashboard screen with tier summary and storage widgets, CLI tui subcommand, test scaffold
- [ ] 04-02-PLAN.md -- Review screen with cluster list + detail split, multi-select bulk actions, auto-triage, propagation toasts, session persistence
- [ ] 04-03-PLAN.md -- Execute screen with dry-run/live progress and Pipeline screen with background workers and log output
- [ ] 04-04-PLAN.md -- Help overlay, theme polish, and end-to-end human verification checkpoint

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Scanning + Metadata Classification | 4/4 | Complete | 2026-03-05 |
| 2. Content Analysis + Full Classification | 3/3 | Complete | 2026-03-05 |
| 3. Report, Review + Safe Execution | 4/4 | Complete | 2026-03-05 |
| 4. Interface & GUI (TUI) | 2/4 | In Progress|  |
