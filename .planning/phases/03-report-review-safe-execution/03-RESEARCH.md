# Phase 3: Report, Review + Safe Execution - Research

**Researched:** 2026-03-05
**Domain:** Terminal UI report generation, interactive review workflows, AppleScript Mail automation, Claude API integration
**Confidence:** HIGH

## Summary

Phase 3 transforms classification data into an actionable cleanup workflow: generating rich reports, walking users through interactive review, executing safe deletions via AppleScript, and optionally calling the Claude API for remaining ambiguous cases. The phase involves four distinct technical domains: Rich terminal rendering with JSON/Markdown export, interactive CLI prompting via questionary, AppleScript-based Mail.app automation through osascript, and Anthropic API integration for metadata-based classification fallback.

The critical blocker from STATE.md (AppleScript message ID mapping to SQLite ROWID) has been **resolved through empirical validation**: Mail.app's AppleScript `id` property is identical to the `messages.ROWID` in the Envelope Index, and the `message id` property (RFC Message-ID string) can be looked up via `message_global_data.message_id_header`. This means messages can be targeted by ROWID directly, which is the fastest approach.

**Primary recommendation:** Use `questionary` for interactive review prompts (arrow-key select, checkbox multi-select), `rich` for report rendering and terminal display, AppleScript `set mailbox of` for safe trash moves targeting by ROWID, and `anthropic` SDK with Haiku 4.5 batch API for cost-effective ambiguous case resolution.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Two-view report:** Tier-first summary for the big picture (Trash/Keep-Active/Keep-Historical/Review with counts, storage, confidence), then cluster-detail view for drill-down within each tier
- **Progressive disclosure:** Start compact (cluster name, email count, storage size, confidence range, 3-5 example subjects), let user expand any group to see full detail (sender breakdown, date range, confidence histogram, top keywords)
- **Triple output:** Rich terminal display for interactive use, plus JSON export for programmatic access, plus Markdown export for human-readable archival
- **Confidence visualization:** Use rich library's built-in bar charts/sparklines for inline confidence distributions per tier and per cluster
- **Review by cluster first**, then drill into individual senders within a cluster for finer control
- **Trash auto-approve:** Auto-approve Trash items above 0.98 confidence; only show the 0.95-0.98 borderline zone for human review
- **Actions per group:** Approve (for deletion), Skip (leave as-is), Reclassify (move to different tier), Split (approve some emails, skip others within same group), Inspect (show individual emails before deciding)
- **Resumable sessions:** Persist review decisions to a file so user can quit and resume later
- **Pre-review auto-triage:** Before interactive review, run automated passes to narrow the Review tier -- auto-resolve obvious clusters, merge similar senders, surface only genuinely ambiguous items
- **Auto-resolution thresholds:** Auto-resolve when EITHER cluster unanimity (all emails same tier, confidence > 0.85) OR sender consistency (all emails from sender same tier, confidence > 0.80) is met
- **Transparency:** Summary with expandable detail -- "Auto-resolved 2,400 emails across 15 clusters. 1,200 emails in 8 clusters need your review."
- **Post-review propagation:** After approving/rejecting a cluster or sender, suggest propagation to similar items (e.g., "You trashed sender X. Also trash 45 emails from their alias Y?"). User confirms each propagation
- **Method:** AppleScript via osascript -- tell Mail.app to move messages to Trash
- **Dry-run by default:** First run shows what WOULD be deleted without doing it. Require explicit `--execute` flag
- **Action log:** SQLite database for audit trail -- each action logged with message_id, subject, sender, tier, action, timestamp, reversible flag
- **Batch size:** Default 100 messages per batch with pause between batches. User-configurable via `--batch-size` flag
- **Claude API trigger:** Suggested after review -- system identifies remaining ambiguous emails and suggests opt-in
- **Payload:** Structured metadata summary -- subject line, sender address, dates, cluster label, 5-10 example subjects from same cluster, plus extracted keywords. No raw body text ever sent
- **Cost transparency:** Calculate and show estimated token cost before proceeding
- **Result integration:** API results update the checkpoint, then show mini-review for final approval

### Claude's Discretion
- AppleScript message targeting strategy (RESOLVED: use ROWID-based `id` lookup)
- Review session file format and location
- Auto-triage pass ordering and implementation details
- Propagation similarity detection algorithm (alias matching, domain grouping, etc.)
- Rich UI layout details for review screens (panel arrangement, color coding per tier)
- Claude API model selection and prompt design for metadata classification
- Exact batch pause duration between AppleScript deletion batches

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EXEC-01 | Generate detailed cleanup report grouped by category with examples and confidence distributions | Rich tables/panels for terminal, JSON serialization for export, Markdown generation for archival. Sparklines via `rich-sparklines` or unicode block chars for confidence histograms |
| EXEC-02 | Interactive terminal walkthrough -- category-by-category review with approve/reject per group | `questionary` library for arrow-key select/checkbox prompts, combined with `rich` for display. Resumable session via JSON state file |
| EXEC-03 | Reversible execution -- move to Trash only, maintain action log with restore capability | AppleScript via `subprocess.run(["osascript", "-e", ...])` targeting messages by ROWID (`id` property). iCloud Trash = "Deleted Messages" mailbox. SQLite action log for audit trail |
| EXEC-04 | Claude API fallback for ambiguous cases (metadata summaries only, never full email bodies) | `anthropic` SDK with Batch API (50% discount). Haiku 4.5 recommended ($0.50/$2.50 per MTok batch). Structured metadata payloads only |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| rich | 14.3.3 | Terminal display, tables, panels, progress, confidence visualization | Already in project, industry standard for terminal UI |
| questionary | 2.1.1 | Interactive prompts: select, checkbox, confirm with arrow-key navigation | Best Python library for interactive CLI prompts; actively maintained |
| anthropic | latest | Claude API client for metadata classification fallback | Official SDK, supports sync/async, batch API |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich-sparklines | latest | Unicode sparkline rendering in Rich tables | Confidence distribution visualization in reports |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| questionary | Rich Prompt/Confirm only | Rich lacks arrow-key navigation, multi-select, and advanced selection UI. questionary is purpose-built for this |
| rich-sparklines | Manual unicode block chars | Manual approach is simpler (fewer deps) but less polished; sparklines library integrates with Rich renderables |
| anthropic batch API | Standard messages.create in loop | Batch API is 50% cheaper, suitable for non-urgent classification of ambiguous emails |

**Installation:**
```bash
uv add questionary anthropic rich-sparklines
```

## Architecture Patterns

### Recommended Project Structure
```
src/icloud_cleanup/
    report.py          # Report generation (JSON, Markdown, terminal)
    review.py          # Interactive review session management
    auto_triage.py     # Pre-review automated resolution passes
    executor.py        # AppleScript deletion execution + action log
    api_fallback.py    # Claude API integration for ambiguous cases
    propagation.py     # Post-review propagation suggestions
```

### Pattern 1: Report Generation (EXEC-01)
**What:** Three-format report from checkpoint data
**When to use:** `icloud_cleanup report` subcommand with `--json`, `--markdown`, `--output` flags
**Example:**
```python
from dataclasses import asdict
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def generate_report(
    classifications: list[Classification],
    messages: list[Message],
    output_dir: Path | None = None,
    format: str = "terminal",  # terminal | json | markdown | all
) -> dict:
    """Generate cleanup report in specified format(s)."""
    # Build report data structure (shared across formats)
    report_data = build_report_data(classifications, messages)

    if format in ("terminal", "all"):
        render_terminal_report(report_data, Console())
    if format in ("json", "all") and output_dir:
        (output_dir / "cleanup_report.json").write_text(
            json.dumps(report_data, indent=2, default=str)
        )
    if format in ("markdown", "all") and output_dir:
        (output_dir / "cleanup_report.md").write_text(
            render_markdown_report(report_data)
        )
    return report_data
```

### Pattern 2: Interactive Review with Resumable Sessions (EXEC-02)
**What:** Cluster-by-cluster review with persistent state
**When to use:** `icloud_cleanup review` subcommand
**Example:**
```python
import questionary
from rich.console import Console

# Review session state persisted as JSON
@dataclass
class ReviewSession:
    session_id: str
    started_at: int
    decisions: dict[int, str]  # cluster_id -> action
    individual_decisions: dict[int, str]  # message_id -> action
    completed: bool = False

def review_cluster(cluster_id: int, emails: list, console: Console) -> str:
    """Present a cluster for review and get user action."""
    # Display cluster summary using Rich
    console.print(Panel(cluster_table, title=f"Cluster: {label}"))

    # Get action via questionary
    action = questionary.select(
        "Action for this cluster:",
        choices=[
            questionary.Choice("Approve for deletion", value="approve"),
            questionary.Choice("Skip (leave as-is)", value="skip"),
            questionary.Choice("Reclassify to different tier", value="reclassify"),
            questionary.Choice("Split (review individually)", value="split"),
            questionary.Choice("Inspect individual emails", value="inspect"),
        ],
    ).ask()
    return action
```

### Pattern 3: AppleScript Execution via osascript (EXEC-03)
**What:** Move messages to Trash via Mail.app AppleScript
**When to use:** After review approval, with `--execute` flag
**Example:**
```python
import subprocess

def move_to_trash_batch(
    rowids: list[int],
    mailbox_name: str = "INBOX",
    account_name: str = "iCloud",
    trash_name: str = "Deleted Messages",
) -> tuple[int, list[str]]:
    """Move messages to Trash via AppleScript. Returns (success_count, errors)."""
    # Build AppleScript for batch (process one at a time for reliability)
    errors = []
    success = 0
    for rowid in rowids:
        script = f'''
tell application "Mail"
    set targetMailbox to mailbox "{mailbox_name}" of account "{account_name}"
    set trashMailbox to mailbox "{trash_name}" of account "{account_name}"
    set matchedMsgs to (every message of targetMailbox whose id is {rowid})
    if (count of matchedMsgs) > 0 then
        set mailbox of item 1 of matchedMsgs to trashMailbox
    end if
end tell'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            success += 1
        else:
            errors.append(f"ROWID {rowid}: {result.stderr.strip()}")
    return success, errors
```

### Pattern 4: Claude API Batch Fallback (EXEC-04)
**What:** Classify remaining ambiguous emails via Claude API
**When to use:** User opts in after review for remaining ambiguous cases
**Example:**
```python
from anthropic import Anthropic

def classify_ambiguous_batch(
    ambiguous_emails: list[dict],  # metadata summaries only
    model: str = "claude-haiku-4-5-20250929",
) -> list[dict]:
    """Submit ambiguous emails to Claude API for classification."""
    client = Anthropic()

    # Build batch requests
    requests = []
    for email in ambiguous_emails:
        requests.append({
            "custom_id": f"msg-{email['message_id']}",
            "params": {
                "model": model,
                "max_tokens": 256,
                "messages": [{"role": "user", "content": build_prompt(email)}],
            },
        })

    # Submit batch (50% discount, up to 24h processing)
    batch = client.messages.batches.create(requests=requests)
    return batch
```

### Anti-Patterns to Avoid
- **Never use AppleScript `delete` command:** It depends on account settings and may permanently delete or behave inconsistently with IMAP. Always use `set mailbox of ... to trashMailbox` for predictable trash moves
- **Never search by `message id` (string) in AppleScript:** It's extremely slow (causes Mail.app timeouts on large mailboxes). Always use numeric `id` (which equals ROWID) for direct lookup
- **Never send raw email bodies to the Claude API:** Privacy violation -- use structured metadata summaries only
- **Never iterate messages in reverse order in AppleScript:** Message indices shift when messages are moved. Process by `id` (ROWID), not by index position
- **Never auto-execute without explicit opt-in:** Dry-run by default, `--execute` flag required

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Interactive CLI prompts | Custom keyboard handler | `questionary` | Arrow-key nav, multi-select, validation, prompt_toolkit-based, handles terminal quirks |
| Terminal rich display | Manual ANSI codes | `rich` (already in project) | Tables, panels, progress, sparklines, colors, Unicode handling |
| Claude API client | Raw HTTP requests | `anthropic` SDK | Handles auth, retries, streaming, batch API, structured responses |
| Confidence histograms | Custom bar rendering | `rich-sparklines` or unicode blocks | Integrates with Rich renderables, handles terminal width |
| Review session persistence | Custom binary format | JSON file + atomic writes (pattern from checkpoint.py) | Human-readable, debuggable, existing pattern in codebase |

**Key insight:** The review flow needs two complementary libraries (questionary for input, rich for display) because neither alone covers both well. Rich has basic Prompt/Confirm but no arrow-key navigation or multi-select. questionary has rich prompts but no table/panel rendering.

## Common Pitfalls

### Pitfall 1: AppleScript id vs message id confusion
**What goes wrong:** Using `message id` (RFC string) for lookups causes Mail.app to hang/timeout on large mailboxes
**Why it happens:** `message id` requires iterating through all messages; `id` (integer = ROWID) allows direct lookup
**How to avoid:** Always use `whose id is {rowid}` -- verified empirically that ROWID = AppleScript `id`
**Warning signs:** AppleScript commands taking > 5 seconds per message

### Pitfall 2: Mail.app Trash mailbox naming
**What goes wrong:** Looking for mailbox named "Trash" fails silently
**Why it happens:** iCloud accounts use "Deleted Messages" as the Trash mailbox name, not "Trash"
**How to avoid:** Use `mailbox "Deleted Messages" of account "iCloud"` -- verified empirically
**Warning signs:** AppleScript returns no errors but messages don't appear in trash

### Pitfall 3: Messages in multiple mailboxes
**What goes wrong:** Script only searches INBOX but messages may be in Archive or custom folders
**Why it happens:** 15,283 messages in INBOX but 1,833 in Archive and others in custom folders
**How to avoid:** Look up the mailbox from the `messages.mailbox` -> `mailboxes.url` mapping, convert URL to AppleScript mailbox path
**Warning signs:** "Message not found" for valid ROWIDs

### Pitfall 4: Mail.app IMAP sync lag
**What goes wrong:** Deleting messages in rapid succession causes Mail.app to not sync properly with IMAP server
**Why it happens:** Each `set mailbox` triggers an IMAP operation; rapid-fire overwhelms the sync queue
**How to avoid:** Process in batches (default 100) with pause between batches (2-5 seconds). User-configurable via `--batch-size`
**Warning signs:** Messages reappearing in INBOX after restart, or appearing in both Trash and original mailbox

### Pitfall 5: questionary + rich console conflict
**What goes wrong:** questionary prompts garble Rich's console output or vice versa
**Why it happens:** Both libraries manage terminal state; questionary uses prompt_toolkit which has its own terminal handling
**How to avoid:** Flush Rich console output before questionary prompt, use separate Console instances or explicit `console.print()` calls between prompts
**Warning signs:** Garbled terminal output, cursor positioning issues

### Pitfall 6: Resumable review session corruption
**What goes wrong:** Session file gets corrupted if user Ctrl-C during write
**Why it happens:** Non-atomic file writes
**How to avoid:** Use the same atomic write pattern as checkpoint.py (write to .tmp, then `os.replace`)
**Warning signs:** JSON parse errors when resuming

### Pitfall 7: Claude API cost surprise
**What goes wrong:** User doesn't realize how many tokens the batch will consume
**Why it happens:** Metadata summaries can be larger than expected when multiplied by thousands of emails
**How to avoid:** Calculate and display estimated cost BEFORE submitting. Require explicit confirmation
**Warning signs:** Token counts much higher than email count suggests

## Code Examples

### AppleScript Message Targeting (verified empirically)
```python
# CONFIRMED: AppleScript `id` property == Envelope Index messages.ROWID
# Example: ROWID 140941 in DB == id 140941 in AppleScript

# Lookup by ROWID (FAST - direct access):
script = '''
tell application "Mail"
    set msgs to (every message of mailbox "INBOX" of account "iCloud" whose id is 140941)
    if (count of msgs) > 0 then
        return subject of item 1 of msgs
    end if
end tell
'''

# Move to Trash (SAFE - uses "Deleted Messages" not "Trash"):
script = '''
tell application "Mail"
    set targetMbox to mailbox "INBOX" of account "iCloud"
    set trashMbox to mailbox "Deleted Messages" of account "iCloud"
    set msgs to (every message of targetMbox whose id is 140941)
    if (count of msgs) > 0 then
        set mailbox of item 1 of msgs to trashMbox
    end if
end tell
'''
```

### RFC Message-ID Header Mapping (verified empirically)
```python
# message_global_data.message_id_header stores RFC Message-ID with angle brackets
# AppleScript `message id` returns the same value without angle brackets
# 99.99% of iCloud messages have message_id_header (25,133 of 25,135)

# To map: strip angle brackets from message_id_header to get AppleScript message id
rfc_id = "<20260305142202.53233294f900b9b3@e.headway.co>"
applescript_msg_id = rfc_id.strip("<>")
# Result: "20260305142202.53233294f900b9b3@e.headway.co"
```

### Mailbox URL to AppleScript Path Conversion
```python
# DB mailbox URLs map to AppleScript mailbox references:
MAILBOX_URL_MAP = {
    "INBOX": 'mailbox "INBOX" of account "iCloud"',
    "Archive": 'mailbox "Archive" of account "iCloud"',
    "Deleted%20Messages": 'mailbox "Deleted Messages" of account "iCloud"',
    # Custom folders like "Events/My Custom Events/DeadMau5" need nested references
}

def url_to_applescript_mailbox(url: str) -> str:
    """Convert Envelope Index mailbox URL to AppleScript reference."""
    # Strip imap://UUID/ prefix, URL-decode
    from urllib.parse import unquote
    path = unquote(url.split("/", 3)[3])  # e.g., "INBOX" or "Events/My Custom Events"
    return f'mailbox "{path}" of account "iCloud"'
```

### Review Session File Format
```json
{
    "session_id": "review_20260305_143022",
    "version": 1,
    "started_at": 1741191022,
    "last_updated": 1741191522,
    "auto_triage": {
        "auto_resolved_count": 2400,
        "auto_resolved_clusters": 15,
        "remaining_review_count": 1200,
        "remaining_review_clusters": 8
    },
    "decisions": {
        "cluster_5": {"action": "approve", "timestamp": 1741191100},
        "cluster_12": {"action": "skip", "timestamp": 1741191200}
    },
    "individual_decisions": {
        "12345": {"action": "approve", "timestamp": 1741191300},
        "12346": {"action": "skip", "timestamp": 1741191301}
    },
    "propagation_applied": [
        {"source": "sender@example.com", "targets": ["alias@example.com"], "action": "approve"}
    ],
    "completed": false
}
```

### Action Log SQLite Schema
```sql
CREATE TABLE action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,       -- links to Envelope Index messages.message_id
    rowid_in_db INTEGER NOT NULL,      -- messages.ROWID (= AppleScript id)
    subject TEXT,
    sender_address TEXT,
    tier TEXT NOT NULL,                 -- classification tier at time of action
    confidence REAL,
    action TEXT NOT NULL,               -- 'move_to_trash', 'restore', 'skip'
    source_mailbox TEXT,               -- original mailbox URL
    timestamp INTEGER NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT 1,
    success BOOLEAN,
    error_message TEXT,
    reversible BOOLEAN NOT NULL DEFAULT 1
);

CREATE INDEX idx_action_log_message_id ON action_log(message_id);
CREATE INDEX idx_action_log_timestamp ON action_log(timestamp);
```

### Cost Estimation for Claude API
```python
def estimate_api_cost(
    emails: list[dict],
    model: str = "claude-haiku-4-5-20250929",
) -> dict:
    """Estimate token cost for batch classification."""
    # Average metadata summary: ~200 tokens input per email
    # Average response: ~50 tokens output per email
    avg_input_tokens = 200
    avg_output_tokens = 50

    total_input = len(emails) * avg_input_tokens
    total_output = len(emails) * avg_output_tokens

    # Haiku 4.5 batch pricing (50% discount)
    BATCH_INPUT_COST = 0.50 / 1_000_000   # $0.50 per MTok
    BATCH_OUTPUT_COST = 2.50 / 1_000_000  # $2.50 per MTok

    input_cost = total_input * BATCH_INPUT_COST
    output_cost = total_output * BATCH_OUTPUT_COST

    return {
        "email_count": len(emails),
        "estimated_input_tokens": total_input,
        "estimated_output_tokens": total_output,
        "estimated_cost_usd": round(input_cost + output_cost, 4),
        "model": model,
        "pricing_type": "batch (50% discount)",
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| AppleScript `delete` command | `set mailbox of ... to trashMailbox` | Long-standing best practice | Predictable IMAP behavior, no accidental permanent delete |
| Search by `message id` (string) | Lookup by `id` (integer = ROWID) | Always faster, now confirmed mapping | Orders of magnitude faster for large mailboxes |
| anthropic SDK sync-only | Batch API with 50% discount | 2025 | Significant cost savings for bulk classification |
| Rich Prompt only | questionary + Rich combination | 2024+ | Arrow-key nav, multi-select not available in Rich alone |

**Deprecated/outdated:**
- `appscript` Python library for AppleScript: abandoned, use `subprocess.run(["osascript", "-e", ...])` instead
- `PyObjC` for Mail: overly complex for this use case, AppleScript via osascript is simpler and sufficient

## Key Discovery: ROWID = AppleScript id (BLOCKER RESOLVED)

The known blocker from STATE.md has been empirically resolved:

| Property | Envelope Index DB | AppleScript Mail.app | Confirmed |
|----------|-------------------|---------------------|-----------|
| ROWID / id | `messages.ROWID` (integer) | `id of message` (integer) | YES -- ROWID 140941 == id 140941 |
| message_id | `messages.message_id` (int64 hash) | N/A (internal to DB) | DB internal, not exposed in AppleScript |
| RFC Message-ID | `message_global_data.message_id_header` (string with `<>`) | `message id of message` (string without `<>`) | YES -- confirmed match |
| IMAP UID | `messages.remote_id` (integer) | N/A | Server-side identifier |

**Recommended targeting strategy:** Use `messages.ROWID` from the Envelope Index and look up via `whose id is {rowid}` in AppleScript. This is the fastest and most reliable approach.

**Mailbox resolution:** The `messages.mailbox` foreign key -> `mailboxes.url` gives the mailbox for each message. Convert the URL path to an AppleScript mailbox reference. Messages are primarily in INBOX (15,283) and Archive (1,833).

## Mailbox Distribution (verified)

| Mailbox | Count | Notes |
|---------|-------|-------|
| INBOX | 15,283 | Primary target |
| Archive | 1,833 | Secondary target |
| Dreamcloud | 54 | Custom folder |
| Events/My Custom Events/DeadMau5 | 28 | Nested custom folder |
| Others | < 5 each | Minimal |

## Open Questions

1. **Batch pause duration between AppleScript operations**
   - What we know: Rapid-fire AppleScript causes IMAP sync issues. Community recommends pausing between batches
   - What's unclear: Optimal duration (1s? 2s? 5s?) -- depends on network and IMAP server
   - Recommendation: Default to 2 seconds between batches of 100, make configurable via `--batch-pause` flag. Log timing data for tuning

2. **Nested mailbox AppleScript syntax for custom folders**
   - What we know: INBOX and Archive work with flat `mailbox "NAME" of account "iCloud"` references
   - What's unclear: Whether nested folders like "Events/My Custom Events" need special AppleScript syntax
   - Recommendation: Test with a simple nested folder lookup during implementation. May need `mailbox "My Custom Events" of mailbox "Events" of account "iCloud"` nesting

3. **questionary + Rich console interaction edge cases**
   - What we know: Both manage terminal state; potential for conflicts
   - What's unclear: Specific failure modes in this project's UI flow
   - Recommendation: Prototype a simple review loop early to catch integration issues

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | Report generation: tier summary, cluster detail, JSON/MD export | unit | `uv run pytest tests/test_report.py -x` | Wave 0 |
| EXEC-01 | Confidence visualization rendering | unit | `uv run pytest tests/test_report.py::test_confidence_viz -x` | Wave 0 |
| EXEC-02 | Review session persistence (save/load/resume) | unit | `uv run pytest tests/test_review.py -x` | Wave 0 |
| EXEC-02 | Auto-triage resolution logic | unit | `uv run pytest tests/test_auto_triage.py -x` | Wave 0 |
| EXEC-02 | Post-review propagation suggestions | unit | `uv run pytest tests/test_propagation.py -x` | Wave 0 |
| EXEC-03 | Action log SQLite operations (create, log, query, restore) | unit | `uv run pytest tests/test_executor.py::test_action_log -x` | Wave 0 |
| EXEC-03 | AppleScript generation (correct syntax, mailbox mapping) | unit | `uv run pytest tests/test_executor.py::test_applescript_generation -x` | Wave 0 |
| EXEC-03 | Dry-run mode (no side effects, correct output) | unit | `uv run pytest tests/test_executor.py::test_dry_run -x` | Wave 0 |
| EXEC-03 | Batch execution with pause logic | unit | `uv run pytest tests/test_executor.py::test_batch_execution -x` | Wave 0 |
| EXEC-04 | Claude API payload construction (metadata only, no bodies) | unit | `uv run pytest tests/test_api_fallback.py::test_payload -x` | Wave 0 |
| EXEC-04 | Cost estimation accuracy | unit | `uv run pytest tests/test_api_fallback.py::test_cost_estimation -x` | Wave 0 |
| EXEC-04 | Result integration back into checkpoint | unit | `uv run pytest tests/test_api_fallback.py::test_result_integration -x` | Wave 0 |
| EXEC-02 | Interactive review flow (questionary prompts) | manual-only | Manual testing -- questionary requires real terminal | N/A |
| EXEC-03 | Actual AppleScript execution against Mail.app | manual-only | Manual testing -- requires Mail.app running with real account | N/A |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_report.py` -- covers EXEC-01 report generation + confidence viz
- [ ] `tests/test_review.py` -- covers EXEC-02 review session persistence
- [ ] `tests/test_auto_triage.py` -- covers EXEC-02 auto-triage resolution
- [ ] `tests/test_propagation.py` -- covers EXEC-02 propagation suggestions
- [ ] `tests/test_executor.py` -- covers EXEC-03 action log, AppleScript generation, dry-run, batch
- [ ] `tests/test_api_fallback.py` -- covers EXEC-04 payload, cost estimation, result integration

## Sources

### Primary (HIGH confidence)
- Empirical validation of ROWID = AppleScript `id` mapping (tested on live Envelope Index + Mail.app)
- Empirical validation of `message_global_data.message_id_header` = RFC Message-ID
- Empirical validation of iCloud Trash = "Deleted Messages" mailbox
- Empirical validation of mailbox distribution (INBOX: 15,283, Archive: 1,833)
- [Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing) -- model costs, batch API 50% discount
- [Anthropic batch API docs](https://platform.claude.com/docs/en/api/creating-message-batches) -- batch request format, 100K limit, 24h processing
- [questionary docs](https://questionary.readthedocs.io/en/stable/pages/types.html) -- question types, parameters
- [Rich prompt docs](https://rich.readthedocs.io/en/stable/prompt.html) -- Prompt, Confirm, IntPrompt classes

### Secondary (MEDIUM confidence)
- [MacScripter: referencing message by message id](https://www.macscripter.net/t/referencing-a-message-with-only-message-id-in-mail/34956) -- `message id` is string (RFC), `id` is integer; `message id` causes timeouts
- [MacScripter: batch moving emails](https://www.macscripter.net/t/batch-moving-emails-in-apple-mail/73203) -- `whose id is in listMoveIds` doesn't work, use repeat loops
- [MacScripter: efficiently delete emails](https://www.macscripter.net/t/efficiently-delete-emails/73031) -- 0.6s per message via loop, batch via flag+filter faster
- [MsgFiler deep dive](https://msgfiler.wordpress.com/2024/02/12/a-deep-dive-into-filing-mail-messages-using-applescript/) -- `set mailbox of` is the correct move approach
- [Apple Community: delete vs move](https://discussions.apple.com/thread/6164090) -- `delete` is account-settings-dependent, inconsistent with IMAP

### Tertiary (LOW confidence)
- Optimal batch pause duration -- community suggests pausing but no authoritative guidance on timing
- Nested mailbox AppleScript syntax -- needs empirical validation for this specific account

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- questionary, rich, anthropic are well-documented, verified via official docs
- Architecture: HIGH -- patterns based on existing codebase conventions (checkpoint.py, display.py, cli.py)
- AppleScript execution: HIGH -- blocker resolved through empirical testing on actual Envelope Index + Mail.app
- Interactive review: MEDIUM -- questionary + rich combination is standard but integration not tested in this specific context
- Claude API: HIGH -- official docs, pricing confirmed, batch API well-documented
- Pitfalls: HIGH -- based on community reports + empirical validation

**Research date:** 2026-03-05
**Valid until:** 2026-04-05 (30 days -- stable domain, no fast-moving dependencies)
