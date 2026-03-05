# Phase 1: Scanning + Metadata Classification - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Scan the local Envelope Index SQLite database, build contact reputation scores from behavioral metadata, and classify every email into one of 4 tiers (Trash / Keep-Active / Keep-Historical / Review) using metadata signals only. No content analysis — that's Phase 2. No execution — that's Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Contact scoring
- **Protection rule:** Any sender you ever replied to or forwarded to is protected from Trash
- **Ratio-based override:** If a protected sender's read/reply rate is below 5%, the reply protection is overridden — catches newsletters you accidentally replied to once but never engaged with again
- **Scoring model:** Combined weighted score using frequency, recency decay, AND behavioral signals (read rate, reply rate, flagged count). Not one or the other — both dimensions.
- **Detection:** Auto-detect contacts from Sent mailbox (7K+ sent messages as ground truth)

### Classification thresholds
- **Aggression level:** Conservative — high bar for Trash (0.95+ confidence), low bar for Keep. Anything uncertain goes to Review for Phase 2 to resolve
- **No pattern shortcuts:** Every email goes through the full scoring pipeline. No hardcoded noreply@ auto-trash or domain blocklists. Consistent and auditable.
- **Apple categories as weak signal:** Query `model_category` from `message_global_data` and include as one low-weight input to scoring. Not trusted, but not ignored either.

### CLI design
- **Structure:** Single script with subcommands — `scan`, `classify`, `report` (not flags like v1)
- **Progress:** `rich` library for animated progress bars with ETA and throughput during scanning
- **Summary output:** Tier breakdown table first (Tier | Count | % | Top senders), then top senders per tier. Both views.
- **Incremental runs:** Checkpoint-based — save last-scanned timestamp, only process new emails on re-run. Must handle merge with previous classification state.

### Claude's Discretion
- Keep-Active vs Keep-Historical split criteria (recency-based, engagement-based, or hybrid — pick based on data distribution)
- Contact detection method (pure Sent mailbox auto-detect, or also add domain-type boosting for personal vs corporate domains)
- Exact weight tuning for combined scoring model
- Rich UI layout details (panel arrangement, color scheme)
- Checkpoint file format and merge strategy

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `~/claude_code_projects/icloud-mail-cleanup/lib/envelope_index.py`: Working DB access module with `open_envelope_index()`, `get_icloud_mailbox_ids()`, `get_icloud_messages()`. Schema joins and iCloud UUID hardcoded. Reference for schema knowledge but write fresh code.

### Established Patterns
- v1 query pattern: `messages` JOIN `mailboxes` ON `m.mailbox = mb.ROWID`, LEFT JOIN `addresses` ON `m.sender = a.ROWID`, LEFT JOIN `subjects` ON `m.subject = s.ROWID`, LEFT JOIN `message_global_data` ON `m.message_id = mgd.message_id`
- Read-only URI mode for DB access: `file:{path}?mode=ro` to avoid WAL lock conflicts with Mail.app
- iCloud UUID: `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`

### Integration Points
- Envelope Index at `~/Library/Mail/V10/MailData/Envelope Index`
- Classification output JSON consumed by Phase 2 (content analysis) and Phase 3 (review + execution)
- `date_received` is standard Unix timestamp (no Apple epoch offset)
- Mailbox URLs: `imap://{UUID}/%` pattern for filtering

</code_context>

<specifics>
## Specific Ideas

- v1 found 25,134 emails with distribution: INBOX 15,283 | Sent 7,183 | Archive 1,832 | Junk 388 | Deleted 251
- v1's Apple category approach classified 671 auto-trash, 1,525 review, 22,938 keep — but 36% uncategorized
- The career-intelligence-engine project considers historical emails as data assets — reinforce protection of old personal/professional emails
- Single account only: user@icloud.com (alias user@me.com)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-scanning-metadata-classification*
*Context gathered: 2026-03-04*
