# Phase 3: Report, Review + Safe Execution - Context

**Gathered:** 2026-03-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can review classification results interactively and execute approved deletions safely with full reversibility. Includes report generation, interactive terminal walkthrough, safe trash-only execution, and Claude API fallback for remaining ambiguous cases. Also includes pre-review auto-triage and post-review propagation passes to minimize human review burden.

</domain>

<decisions>
## Implementation Decisions

### Report format & content
- **Two-view report:** Tier-first summary for the big picture (Trash/Keep-Active/Keep-Historical/Review with counts, storage, confidence), then cluster-detail view for drill-down within each tier
- **Progressive disclosure:** Start compact (cluster name, email count, storage size, confidence range, 3-5 example subjects), let user expand any group to see full detail (sender breakdown, date range, confidence histogram, top keywords)
- **Triple output:** Rich terminal display for interactive use, plus JSON export for programmatic access, plus Markdown export for human-readable archival
- **Confidence visualization:** Use rich library's built-in bar charts/sparklines for inline confidence distributions per tier and per cluster

### Interactive review flow
- **Granularity:** Review by cluster first, then drill into individual senders within a cluster for finer control
- **Trash auto-approve:** Auto-approve Trash items above 0.98 confidence; only show the 0.95-0.98 borderline zone for human review
- **Actions per group:** Approve (for deletion), Skip (leave as-is), Reclassify (move to different tier), Split (approve some emails, skip others within same group), Inspect (show individual emails before deciding)
- **Resumable sessions:** Persist review decisions to a file so user can quit and resume later — critical for 6K+ Review-tier emails

### Iteration & refinement passes
- **Pre-review auto-triage:** Before interactive review, run automated passes to narrow the Review tier — auto-resolve obvious clusters, merge similar senders, surface only genuinely ambiguous items
- **Auto-resolution thresholds:** Auto-resolve when EITHER cluster unanimity (all emails same tier, confidence > 0.85) OR sender consistency (all emails from sender same tier, confidence > 0.80) is met
- **Transparency:** Summary with expandable detail — "Auto-resolved 2,400 emails across 15 clusters. 1,200 emails in 8 clusters need your review." User can inspect auto-resolved items if desired
- **Post-review propagation:** After approving/rejecting a cluster or sender, suggest propagation to similar items (e.g., "You trashed sender X. Also trash 45 emails from their alias Y?"). User confirms each propagation — no automatic application

### Deletion execution & safety
- **Method:** AppleScript via osascript — tell Mail.app to move messages to Trash. Goes through Mail's own logic for maximum safety. Requires validating ROWID-to-message mapping empirically (known blocker from STATE.md)
- **Dry-run by default:** First run shows what WOULD be deleted without doing it. Require explicit `--execute` flag to actually carry out deletions
- **Action log:** SQLite database for audit trail — each action logged with message_id, subject, sender, tier, action, timestamp, reversible flag. Queryable for restore operations
- **Batch size:** Default 100 messages per batch with pause between batches (let Mail.app sync). User-configurable via `--batch-size` flag

### Claude API fallback
- **Trigger:** Suggested after review — system identifies remaining ambiguous emails and suggests "N emails remain ambiguous — want to run Claude analysis?" User opts in for the batch
- **Payload:** Structured metadata summary — subject line, sender address, dates, cluster label, 5-10 example subjects from same cluster, plus extracted keywords from body. No raw body text ever sent
- **Cost transparency:** Calculate and show estimated token cost based on payload size x email count. Require user confirmation before proceeding
- **Result integration:** API results update the checkpoint, then show a mini-review of just the reclassified emails for final approval before any action

### Claude's Discretion
- AppleScript message targeting strategy (message ID vs subject+date matching for ROWID mapping)
- Review session file format and location
- Auto-triage pass ordering and implementation details
- Propagation similarity detection algorithm (alias matching, domain grouping, etc.)
- Rich UI layout details for review screens (panel arrangement, color coding per tier)
- Claude API model selection and prompt design for metadata classification
- Exact batch pause duration between AppleScript deletion batches

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `display.py`: `display_tier_summary()`, `display_top_senders()`, `display_cluster_summary()`, `display_reclassification_summary()` — extend for report generation
- `checkpoint.py`: `save_checkpoint()`, `load_checkpoint()`, `merge_checkpoint()` — JSONL interchange format for reading Phase 2 results and writing back reclassifications
- `models.py`: `Classification` dataclass with `tier`, `confidence`, `cluster_id`, `cluster_label`, `content_score` — all fields needed for report and review
- `cli.py`: Existing `cmd_report()` subcommand shows tier summary + top senders — extend or add new subcommands (`review`, `execute`)
- `scanner.py`: `open_db()`, `scan_messages()` — needed for sender/subject lookup during report and review
- `rich` library already in use for progress bars, tables, console output

### Established Patterns
- Subcommand-based CLI (`scan`, `classify`, `analyze`, `report`)
- Dataclass-based domain models with type hints
- Signal-based scoring with `SignalResult` (name/value/weight/explanation)
- Atomic file writes via tmp + `os.replace`
- Read-only DB access via `file:{path}?mode=ro` URI
- Checkpoint JSONL as data interchange between phases

### Integration Points
- Phase 2 checkpoint JSONL is the input — contains all classifications with cluster assignments
- `Message.message_id` links DB records for sender/subject lookup
- New CLI subcommands: `review` (interactive walkthrough), `execute` (carry out deletions)
- AppleScript execution requires Mail.app to be running
- SQLite action log is a new artifact (separate from checkpoint and Envelope Index)

</code_context>

<specifics>
## Specific Ideas

- Phase 1 classified ~24K emails: 2 trash, 114 keep_active, 18,399 keep_historical, 6,050 review — the review tier is large and needs aggressive auto-triage to be manageable
- Phase 2 added content analysis with ~30 semantic clusters — these clusters drive the review grouping
- Known blocker: AppleScript message ID to SQLite ROWID mapping is undocumented — must validate empirically before writing execution code
- The review session state and the action log are the two new persistent artifacts this phase creates

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-report-review-safe-execution*
*Context gathered: 2026-03-05*
