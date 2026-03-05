# Phase 1: Scanning + Metadata Classification - Research

**Researched:** 2026-03-04
**Domain:** Apple Mail Envelope Index SQLite schema, email classification scoring, Python CLI
**Confidence:** HIGH

## Summary

Phase 1 reads the local Envelope Index SQLite database (~25K emails), builds a contact reputation model from behavioral metadata, and classifies every email into 4 tiers (Trash / Keep-Active / Keep-Historical / Review) using metadata signals only. The database schema has been empirically verified against the live database and provides rich signals: read status, replied flags (bit 2 of `flags` field), forwarded flags, conversation threading, Apple Intelligence categories (weak signal), `list_id_hash` for newsletter detection, and `automated_conversation` flags. The Sent mailbox (7,183 messages to 999 unique recipients) serves as ground truth for contact detection, yielding 597 bidirectional contacts out of 1,540 unique INBOX senders.

The scoring model combines frequency, recency decay, and behavioral engagement signals (read rate, reply history, flagged count) into a 0-1 confidence score per email. The key technical challenge is tuning the weights so that the conservative threshold (0.95+ for Trash) produces a high-precision trash tier while deferring ambiguous cases to Review. With 25K emails, the entire scan completes in under a second via SQLite, so no streaming/chunking needed — just a progress bar for UX.

**Primary recommendation:** Use `argparse` subcommands + `rich` for CLI (minimal deps), conversation-based reply detection as primary signal (catches 6,841 messages vs 2,884 from flag bit alone), and a weighted scoring model with exponential recency decay.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Protection rule:** Any sender you ever replied to or forwarded to is protected from Trash
- **Ratio-based override:** If a protected sender's read/reply rate is below 5%, the reply protection is overridden -- catches newsletters you accidentally replied to once but never engaged with again
- **Scoring model:** Combined weighted score using frequency, recency decay, AND behavioral signals (read rate, reply rate, flagged count). Not one or the other -- both dimensions.
- **Detection:** Auto-detect contacts from Sent mailbox (7K+ sent messages as ground truth)
- **Aggression level:** Conservative -- high bar for Trash (0.95+ confidence), low bar for Keep. Anything uncertain goes to Review for Phase 2 to resolve
- **No pattern shortcuts:** Every email goes through the full scoring pipeline. No hardcoded noreply@ auto-trash or domain blocklists. Consistent and auditable.
- **Apple categories as weak signal:** Query `model_category` from `message_global_data` and include as one low-weight input to scoring. Not trusted, but not ignored either.
- **CLI structure:** Single script with subcommands -- `scan`, `classify`, `report` (not flags like v1)
- **Progress:** `rich` library for animated progress bars with ETA and throughput during scanning
- **Summary output:** Tier breakdown table first (Tier | Count | % | Top senders), then top senders per tier. Both views.
- **Incremental runs:** Checkpoint-based -- save last-scanned timestamp, only process new emails on re-run. Must handle merge with previous classification state.

### Claude's Discretion
- Keep-Active vs Keep-Historical split criteria (recency-based, engagement-based, or hybrid -- pick based on data distribution)
- Contact detection method (pure Sent mailbox auto-detect, or also add domain-type boosting for personal vs corporate domains)
- Exact weight tuning for combined scoring model
- Rich UI layout details (panel arrangement, color scheme)
- Checkpoint file format and merge strategy

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCAN-01 | Scan Envelope Index SQLite DB read-only for user@icloud.com | DB path, read-only URI mode, iCloud UUID, mailbox URL pattern all verified empirically |
| SCAN-02 | Calculate volume statistics per sender (count, storage, date range, last received) | Query pattern verified: GROUP BY sender with SUM(size), MIN/MAX(date_received) |
| SCAN-03 | Display progress bar with count/total and ETA during all long-running operations | rich 14.3.3 Progress.track() with MofNCompleteColumn + TimeRemainingColumn |
| CSIG-01 | Score each contact by reply history, frequency, recency, and bidirectional communication | Sent mailbox yields 999 unique recipients; conversation_id threading for reply detection; flags bit 2 for replied status |
| CSIG-02 | Extract behavioral signals from flags (read, replied, flagged, forwarded, ignored, deleted patterns) | Empirically verified: `read` column (0/1), `flagged` column (0/1), `deleted` column (0/1), flags bit 2 = replied, flags bit 4 = forwarded, `automated_conversation` column |
| CLAS-01 | Classify every email into 4 tiers: Trash / Keep-Active / Keep-Historical / Review | Scoring model architecture documented with signal weights and threshold strategy |
| CLAS-02 | Assign 0-1 confidence score per email with explanation of contributing signals | Signal decomposition approach: each signal produces a sub-score, weighted combination yields final 0-1 score, explanation tracks which signals contributed |
| CLAS-03 | Two-pass strategy -- metadata-only first pass, MLX embeddings only for ambiguous remainder | Phase 1 IS the metadata-only first pass; Review tier collects ambiguous emails for Phase 2 |
| CLAS-04 | Protect personal/historical emails with asymmetric threshold (0.95+ to trash) | Protection rules from CONTEXT.md: reply/forward protection, ratio-based override, 0.95+ threshold for Trash |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlite3 | stdlib | Read-only Envelope Index DB access | No external dependency needed; URI mode for read-only |
| rich | 14.3.3 | Progress bars, tables, terminal UI | User-specified; de facto Python terminal UI library |
| argparse | stdlib | CLI subcommands (scan/classify/report) | Sufficient for 3 subcommands; no extra dependency |
| pathlib | stdlib | File path handling | User preference per CLAUDE.md |
| json | stdlib | Checkpoint read/write | Lightweight, human-readable |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | Typed data structures for messages, contacts, classifications | Everywhere - all domain objects |
| collections.Counter | stdlib | Frequency counting for sender stats | Sender volume aggregation |
| math | stdlib | Exponential decay calculation | Recency scoring |
| datetime | stdlib | Timestamp conversion and age calculation | Date range display, recency decay |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| argparse | click/typer | Extra dependency for only 3 subcommands; not justified |
| json checkpoint | sqlite checkpoint | JSON is human-editable, more transparent for debugging |
| pandas | manual aggregation | 25K rows doesn't need pandas overhead; stdlib Counter is sufficient |

**Installation:**
```bash
uv init
uv add rich
```

## Architecture Patterns

### Recommended Project Structure
```
src/
  icloud_cleanup/
    __init__.py
    cli.py            # argparse setup, subcommand dispatch
    scanner.py         # DB access, raw message extraction
    contacts.py        # Contact reputation model from Sent mailbox
    classifier.py      # Scoring engine, tier assignment
    checkpoint.py      # Save/load/merge classification state
    models.py          # Dataclasses: Message, Contact, Classification
    display.py         # Rich tables, progress bars, report formatting
```

### Pattern 1: Read-Only Database Access
**What:** Open Envelope Index in URI read-only mode to avoid WAL lock conflicts with Mail.app
**When to use:** Every database access
**Example:**
```python
# Source: verified from v1 + empirical testing
import sqlite3
from pathlib import Path

ENVELOPE_INDEX = Path.home() / "Library/Mail/V10/MailData/Envelope Index"
ICLOUD_UUID = "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"

def open_db() -> sqlite3.Connection:
    uri = f"file:{ENVELOPE_INDEX}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
```

### Pattern 2: Two-Phase Contact Detection
**What:** Build contact reputation from Sent mailbox recipients first, then score incoming messages
**When to use:** Before classification begins
**Example:**
```python
# Phase A: Extract known contacts from Sent folder
# 7,183 sent messages -> 999 unique recipients
sent_recipients_query = """
SELECT a.address, COUNT(*) as send_count,
  MAX(m.date_received) as last_sent_to
FROM messages m
JOIN mailboxes mb ON m.mailbox = mb.ROWID
JOIN recipients r ON r.message = m.ROWID
JOIN addresses a ON r.address = a.ROWID
WHERE mb.url LIKE 'imap://{uuid}/Sent%'
GROUP BY LOWER(a.address)
""".format(uuid=ICLOUD_UUID)

# Phase B: For each INBOX sender, check if they're in the contacts set
# and find conversation overlap (bidirectional communication)
```

### Pattern 3: Conversation-Based Reply Detection
**What:** Use `conversation_id` to detect if user replied to a sender, not just per-message flags
**When to use:** Building the reply protection signal
**Rationale:** Flag bit 2 only marks 2,884 INBOX messages as replied. Conversation-based detection catches 6,841 messages in threads where user has Sent messages -- 2.4x more coverage.
**Example:**
```python
# Get all conversation_ids that have messages in Sent
replied_conversations = """
SELECT DISTINCT conversation_id
FROM messages m
JOIN mailboxes mb ON m.mailbox = mb.ROWID
WHERE mb.url LIKE 'imap://{uuid}/Sent%'
AND conversation_id > 0
""".format(uuid=ICLOUD_UUID)

# Both methods should be combined:
# 1. conversation_id match (catches thread-level replies)
# 2. flags & 0x4 on the specific message (catches direct replies)
```

### Pattern 4: Weighted Composite Scoring
**What:** Each signal produces a 0-1 sub-score; weighted combination produces final score
**When to use:** Classification of every message
**Example:**
```python
@dataclass
class SignalResult:
    name: str
    value: float       # 0.0 to 1.0
    weight: float      # relative importance
    explanation: str   # human-readable

# Combine signals into final score
def compute_confidence(signals: list[SignalResult]) -> tuple[float, str]:
    total_weight = sum(s.weight for s in signals)
    score = sum(s.value * s.weight for s in signals) / total_weight
    explanation = "; ".join(
        f"{s.name}={s.value:.2f}" for s in signals if s.value > 0
    )
    return score, explanation
```

### Anti-Patterns to Avoid
- **Hardcoded sender blocklists:** User explicitly prohibited pattern shortcuts. Every email goes through the full scoring pipeline.
- **Trusting Apple categories as primary signal:** They're unreliable (36% uncategorized, frequent miscategorization). Use only as a weak/low-weight input.
- **Querying the DB per-message:** Fetch all data in bulk queries, process in Python. SQLite is fast but connection overhead per-message would be wasteful.
- **Modifying the Envelope Index:** Read-only mode is non-negotiable. Any write attempt would corrupt Mail.app's database.

## Envelope Index Schema Reference (Empirically Verified)

### Core Tables and Joins
```sql
-- The canonical query joining all needed tables
SELECT
    m.ROWID,
    m.message_id,
    m.conversation_id,
    m.flags,
    m.read,
    m.flagged,
    m.deleted,
    m.size,
    m.date_received,
    m.date_sent,
    m.date_last_viewed,
    m.list_id_hash,
    m.unsubscribe_type,
    m.automated_conversation,
    COALESCE(a.address, '') as sender_address,
    COALESCE(s.subject, '') as subject,
    mb.url as mailbox_url,
    mgd.model_category,
    mgd.model_high_impact
FROM messages m
JOIN mailboxes mb ON m.mailbox = mb.ROWID
LEFT JOIN addresses a ON m.sender = a.ROWID
LEFT JOIN subjects s ON m.subject = s.ROWID
LEFT JOIN message_global_data mgd ON m.message_id = mgd.message_id
WHERE mb.url LIKE 'imap://XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/%'
```

### Key Column Meanings (Empirically Verified)

| Column | Table | Type | Verified Values | Notes |
|--------|-------|------|----------------|-------|
| read | messages | int | 0=unread, 1=read | 23,942 read / 1,193 unread |
| flagged | messages | int | 0=no, 1=flagged | 25,101 unflagged / 34 flagged |
| deleted | messages | int | 0=no, 1=deleted | 25,134 not-deleted / 1 deleted |
| flags & 0x4 | messages | bitmask | bit 2 = replied | 2,884 INBOX msgs with bit set; 96% correlation with conversation-reply |
| flags & 0x10 | messages | bitmask | bit 4 = forwarded | 33 INBOX msgs with bit set |
| conversation_id | messages | int | thread grouping | 10,656 single-msg convos, 3,056 with 2-5 msgs, 610 with 6-20, 30 with 20+ |
| date_received | messages | int | Unix timestamp | Standard epoch, NOT Apple Core Data epoch |
| date_last_viewed | messages | int or NULL | Unix timestamp | Only 224 of 25,135 have values -- sparse, not reliable |
| list_id_hash | messages | int or NULL | Mailing list ID hash | All 25,135 have values -- useful for newsletter grouping |
| unsubscribe_type | messages | int or NULL | Unsubscribe header type | 23,446 NULL, 1,531 type 0, 121 type 7, etc. |
| automated_conversation | messages | int | 0=human, 1/2=automated | 22,808 type 0, 2,295 type 2, 32 type 1 |
| model_category | message_global_data | int or NULL | Apple Intelligence category | 0=Primary(12,439), 1=Transactions(119), 2=Updates(1,581), 3=Promotions(1,871), NULL=Uncategorized(9,125) |
| model_high_impact | message_global_data | int | High-impact flag | 24,746 not-high-impact / 387 high-impact |
| message_id | messages/message_global_data | int | Join key | NOT ROWID -- use messages.message_id = message_global_data.message_id |
| size | messages | int | Bytes | Approximate message size |

### Data Distribution Summary (Live Database)

| Metric | Value |
|--------|-------|
| Total iCloud emails | 25,135 |
| INBOX | 15,283 |
| Sent | 7,183 |
| Archive | 1,832 |
| Junk | 388 |
| Deleted | 251 |
| Unique INBOX senders | 1,540 |
| Unique sender domains | 801 |
| Unique Sent recipients | 999 |
| Bidirectional contacts (sent to AND received from) | 597 (39% of INBOX senders) |
| Messages with replied flag (bit 2) | 2,884 |
| Messages in replied conversations | 6,841 |
| Messages flagged by user | 34 |
| Apple Intelligence categorized | 16,010 (64%) |
| Apple Intelligence uncategorized | 9,125 (36%) |
| Apple high-impact flagged | 387 |
| automated_conversation type 2 | 2,295 |
| Conversations with user replies (bidirectional) | 2,860 |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Terminal progress bars | Custom print-based progress | rich.progress.Progress | Handles terminal width, ETA calculation, thread safety |
| Terminal tables | Custom string formatting | rich.table.Table | Auto-wraps columns, handles alignment, styling |
| Email address normalization | String splitting | LOWER() in SQL + strip() | Case-insensitive matching is critical; addresses.address is COLLATE NOCASE |
| Exponential decay | Custom time math | `math.exp(-lambda * age_days)` | Standard decay function, well-understood parameter tuning |
| JSON checkpoint merge | Custom diffing | dict.update() with timestamp comparison | Simple last-write-wins per message_id |

**Key insight:** The Envelope Index does all the heavy lifting. Don't replicate its indexing or joins in Python -- let SQLite handle grouping and aggregation, bring results into Python only for scoring logic.

## Common Pitfalls

### Pitfall 1: WAL Lock Conflicts with Mail.app
**What goes wrong:** Opening the database in write mode or without URI read-only mode causes WAL lock conflicts. Mail.app may crash or the query may fail.
**Why it happens:** Mail.app has the database open with WAL journaling mode.
**How to avoid:** Always use `file:{path}?mode=ro` URI mode. Never attempt writes.
**Warning signs:** `sqlite3.OperationalError: database is locked`

### Pitfall 2: message_id vs ROWID Confusion
**What goes wrong:** Using ROWID to join messages to message_global_data gives wrong results or no matches.
**Why it happens:** The join key is `messages.message_id = message_global_data.message_id`, NOT ROWID.
**How to avoid:** Always use the `message_id` column for cross-table joins.
**Warning signs:** Unexpectedly low match counts when joining to message_global_data.

### Pitfall 3: Flags Field is Not Simple IMAP Bitmask
**What goes wrong:** Treating the `flags` field as a standard IMAP flag set gives incorrect results because the values are large 64-bit integers with Apple-specific encoding.
**Why it happens:** Apple uses the flags field for multiple purposes with different bit ranges.
**How to avoid:** Use only the empirically verified bits: `flags & 0x4` for replied, `flags & 0x10` for forwarded. Use the dedicated `read`, `flagged`, `deleted` columns instead of trying to extract these from `flags`.
**Warning signs:** Flag values in the billions (e.g., 8590195840) that don't match IMAP flag definitions.

### Pitfall 4: Reply Detection from Flags Alone Misses 60% of Replies
**What goes wrong:** Using only `flags & 0x4` detects only 2,884 replied messages; conversation-based detection catches 6,841.
**Why it happens:** The replied flag is only set on the specific message that was replied to, not all messages in a conversation thread. Also, some replies may not set the flag.
**How to avoid:** Combine both methods: `flags & 0x4` (per-message) UNION conversation_id overlap with Sent mailbox (thread-level).
**Warning signs:** Low reply counts relative to Sent message volume.

### Pitfall 5: Case Sensitivity in Email Addresses
**What goes wrong:** `friend@example.com` and `Friend@example.com` treated as different senders.
**Why it happens:** The `addresses` table uses `COLLATE NOCASE` for uniqueness but stores original case. Python string comparison is case-sensitive by default.
**How to avoid:** Always normalize with `LOWER()` in SQL or `.lower()` in Python when grouping/comparing addresses.
**Warning signs:** Same person appearing as multiple senders with different message counts.

### Pitfall 6: date_last_viewed is Useless for Engagement Tracking
**What goes wrong:** Relying on `date_last_viewed` as a signal for whether the user engaged with a message.
**Why it happens:** Only 224 of 25,135 messages have this field populated (0.9%). It's not reliably set by Mail.app.
**How to avoid:** Use `read` column (0/1) instead. It has full coverage (23,942 read / 1,193 unread).
**Warning signs:** Most messages having NULL date_last_viewed.

### Pitfall 7: senders/sender_addresses Tables are Sparse
**What goes wrong:** Relying on the `senders` table with `contact_identifier` for Apple Contacts integration.
**Why it happens:** This table only has ~15 entries total -- it does not cover all senders.
**How to avoid:** Use the Sent mailbox recipient approach for contact detection. The senders table is not useful.
**Warning signs:** Very low contact match rates.

## Code Examples

### Scanning All iCloud Messages (Bulk Extract)
```python
# Source: empirically verified against live Envelope Index
def scan_messages(conn: sqlite3.Connection) -> list[dict]:
    query = """
    SELECT
        m.ROWID as rowid,
        m.message_id,
        m.conversation_id,
        m.flags,
        m.read,
        m.flagged,
        m.deleted,
        m.size,
        m.date_received,
        m.list_id_hash,
        m.unsubscribe_type,
        m.automated_conversation,
        COALESCE(a.address, '') as sender_address,
        COALESCE(s.subject, '') as subject,
        mb.url as mailbox_url,
        mgd.model_category,
        mgd.model_high_impact
    FROM messages m
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    LEFT JOIN addresses a ON m.sender = a.ROWID
    LEFT JOIN subjects s ON m.subject = s.ROWID
    LEFT JOIN message_global_data mgd ON m.message_id = mgd.message_id
    WHERE mb.url LIKE ?
    ORDER BY m.date_received DESC
    """
    cursor = conn.execute(query, (f"imap://{ICLOUD_UUID}/%",))
    return [dict(row) for row in cursor]
```

### Building Contact Reputation from Sent Mailbox
```python
# Source: empirically verified query patterns
def build_contact_map(conn: sqlite3.Connection) -> dict[str, ContactProfile]:
    # Step 1: Get all Sent recipients with frequency
    sent_query = """
    SELECT LOWER(a.address) as address,
           COUNT(*) as times_sent_to,
           MAX(m.date_received) as last_sent_to
    FROM messages m
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    JOIN recipients r ON r.message = m.ROWID
    JOIN addresses a ON r.address = a.ROWID
    WHERE mb.url LIKE ?
    GROUP BY LOWER(a.address)
    """
    # Step 2: Get conversation_ids from Sent for reply detection
    conv_query = """
    SELECT DISTINCT conversation_id
    FROM messages m
    JOIN mailboxes mb ON m.mailbox = mb.ROWID
    WHERE mb.url LIKE ?
    AND conversation_id > 0
    """
    # ... build ContactProfile objects
```

### Rich Progress Bar for Scanning
```python
# Source: rich 14.x official docs
from rich.progress import Progress, SpinnerColumn, MofNCompleteColumn, TimeRemainingColumn

def scan_with_progress(messages: list[dict]) -> list[Classification]:
    results = []
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Classifying...", total=len(messages))
        for msg in messages:
            result = classify_message(msg)
            results.append(result)
            progress.update(task, advance=1)
    return results
```

### Rich Summary Table
```python
# Source: rich 14.x official docs
from rich.console import Console
from rich.table import Table

def display_tier_summary(tiers: dict[str, list]) -> None:
    console = Console()
    table = Table(title="Classification Summary")
    table.add_column("Tier", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("%", justify="right")
    table.add_column("Top Senders", style="dim")

    total = sum(len(v) for v in tiers.values())
    for tier_name, msgs in tiers.items():
        pct = f"{len(msgs) / total * 100:.1f}%"
        top = ", ".join(top_senders(msgs, 3))
        table.add_row(tier_name, str(len(msgs)), pct, top)

    console.print(table)
```

## Scoring Model Architecture

### Signal Definitions

| Signal | Source | Range | Weight (suggested) | Direction |
|--------|--------|-------|--------------------|-----------|
| contact_score | Sent mailbox, conversation overlap | 0-1 | 0.30 | Higher = more keep-worthy |
| frequency_score | Message count per sender | 0-1 | 0.15 | Normalized; high freq newsletters score low via engagement ratio |
| recency_score | Exponential decay from last received | 0-1 | 0.15 | exp(-lambda * age_days), lambda ~0.003 for 1-year half-life |
| read_rate | read messages / total from sender | 0-1 | 0.15 | Higher = user engages with this sender |
| reply_rate | replied messages / total from sender | 0-1 | 0.10 | Higher = bidirectional relationship |
| apple_category | model_category from message_global_data | 0-1 | 0.05 | Primary/Transactions boost, Promotions penalty |
| automation_signal | automated_conversation + list_id_hash | 0-1 | 0.05 | Automated = lower value |
| flagged_boost | User flagged any message from sender | 0/1 | 0.05 | Binary boost if user ever flagged |

### Protection Logic (Before Scoring)
```
1. Is sender in Sent recipients? -> protected = True
2. Is message in conversation with Sent message? -> protected = True
3. Is message flags & 0x4 (replied)? -> protected = True
4. Is message flags & 0x10 (forwarded)? -> protected = True
5. If protected AND sender read_rate < 5%:
   -> override protection (catches newsletter-replied-once case)
6. If protected (not overridden): CANNOT be classified as Trash
```

### Tier Assignment Logic
```
IF protected (not overridden):
    IF high engagement (score > 0.6): Keep-Active
    IF low engagement but historical: Keep-Historical
    ELSE: Review

IF NOT protected:
    IF trash_confidence >= 0.95: Trash
    IF keep_confidence >= 0.7: Keep-Active or Keep-Historical
    ELSE: Review (deferred to Phase 2)
```

### Keep-Active vs Keep-Historical Split (Claude's Discretion)
**Recommendation: Hybrid approach** based on the data distribution.
- **Keep-Active**: Last received within 180 days AND (read_rate > 50% OR reply_rate > 10%)
- **Keep-Historical**: Older than 180 days OR low engagement but from a known contact
- **Rationale**: Pure recency misses old friends who stopped emailing. Pure engagement misses recent legitimate emails the user hasn't read yet. Hybrid catches both cases.

## Checkpoint Format (Claude's Discretion)

**Recommendation: JSON Lines (.jsonl)** format for the classification checkpoint.

```json
{"message_id": 12345, "tier": "trash", "confidence": 0.97, "signals": "contact=0.0; read_rate=0.0; frequency=0.8", "protected": false, "timestamp": 1709600000}
{"message_id": 12346, "tier": "keep-active", "confidence": 0.85, "signals": "contact=0.9; read_rate=0.8; reply=0.3", "protected": true, "timestamp": 1709600000}
```

**Why JSONL over plain JSON:**
- Appendable without rewriting the entire file (incremental runs)
- Readable line-by-line without loading full dataset
- Easy to merge: read all lines, index by message_id, last-write-wins by timestamp
- Phase 2 and Phase 3 can read it directly

**Merge strategy for incremental runs:**
1. Load existing checkpoint into `dict[message_id, Classification]`
2. Scan for new messages (date_received > last_scan_timestamp)
3. Classify new messages, merge into dict
4. Re-classify if scoring model changed (version flag in checkpoint header)
5. Write complete checkpoint (atomic: write to .tmp, rename)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Apple Mail categories alone | Multi-signal metadata scoring | This project | 36% uncategorized problem eliminated |
| IMAP flag bits for reply detection | Conversation-based + flag hybrid | Discovered during research | 2.4x more reply coverage (6,841 vs 2,884) |
| Per-message DB queries | Bulk extract + Python processing | v2 architecture | Sub-second full scan vs per-message overhead |
| Hardcoded sender blocklists | Universal scoring pipeline | User decision | Consistent, auditable, no edge case gaps |

**Deprecated/outdated:**
- v1 approach using Apple Intelligence categories as primary classifier -- 36% uncategorized, frequent miscategorization
- The `senders` / `sender_addresses` tables for contact detection -- only ~15 entries, not useful

## Open Questions

1. **Exact weight tuning for scoring model**
   - What we know: Signal structure defined, relative importance roughly understood
   - What's unclear: Optimal weights require empirical testing against the 25K dataset
   - Recommendation: Start with suggested weights, add a `--debug-scores` flag to dump per-sender signal breakdowns, tune iteratively after first run

2. **list_id_hash interpretation**
   - What we know: All 25,135 messages have a value for this field
   - What's unclear: Whether NULL vs non-NULL or specific hash values identify mailing lists
   - Recommendation: Investigate in implementation -- group messages by list_id_hash and check if it clusters newsletters/mailing lists distinctly from personal email

3. **unsubscribe_type values**
   - What we know: Values include NULL (23,446), 0 (1,531), 7 (121), 1 (19), 6 (9), 3 (7), 2 (2)
   - What's unclear: What each integer means (mailto vs URL vs one-click)
   - Recommendation: Treat non-NULL unsubscribe_type as a weak "newsletter" signal; don't try to interpret specific values

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (standard for Python projects) |
| Config file | none -- Wave 0 |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCAN-01 | Opens Envelope Index read-only, filters to iCloud UUID | unit | `uv run pytest tests/test_scanner.py::test_open_db_readonly -x` | No -- Wave 0 |
| SCAN-02 | Produces sender stats with count, size, date range | unit | `uv run pytest tests/test_scanner.py::test_sender_stats -x` | No -- Wave 0 |
| SCAN-03 | Progress bar renders during scan | manual-only | Manual: run `uv run python -m icloud_cleanup.cli scan` and visually confirm progress bar | N/A |
| CSIG-01 | Contact scoring from Sent mailbox with reply/freq/recency | unit | `uv run pytest tests/test_contacts.py::test_contact_scoring -x` | No -- Wave 0 |
| CSIG-02 | Behavioral signals extracted (read, replied, flagged, forwarded) | unit | `uv run pytest tests/test_contacts.py::test_behavioral_signals -x` | No -- Wave 0 |
| CLAS-01 | Every message classified into exactly one of 4 tiers | unit | `uv run pytest tests/test_classifier.py::test_tier_assignment -x` | No -- Wave 0 |
| CLAS-02 | Confidence score 0-1 with signal explanation | unit | `uv run pytest tests/test_classifier.py::test_confidence_score -x` | No -- Wave 0 |
| CLAS-03 | Metadata-only pass defers ambiguous to Review | unit | `uv run pytest tests/test_classifier.py::test_review_deferral -x` | No -- Wave 0 |
| CLAS-04 | Protected contacts never classified as Trash (unless override) | unit | `uv run pytest tests/test_classifier.py::test_protection_rules -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` -- shared fixtures (mock DB connection, sample messages, sample contacts)
- [ ] `tests/test_scanner.py` -- covers SCAN-01, SCAN-02
- [ ] `tests/test_contacts.py` -- covers CSIG-01, CSIG-02
- [ ] `tests/test_classifier.py` -- covers CLAS-01, CLAS-02, CLAS-03, CLAS-04
- [ ] `pyproject.toml` -- pytest config section
- [ ] Framework install: `uv add --dev pytest`

**Testing strategy note:** Tests should use an in-memory SQLite database with a fixture that creates the Envelope Index schema and populates it with controlled test data (known senders, known conversations, known flag states). Do NOT test against the live Envelope Index -- it's read-only and environment-specific.

## Sources

### Primary (HIGH confidence)
- Live Envelope Index database at `~/Library/Mail/V10/MailData/Envelope Index` -- all schema, column values, data distributions empirically verified via direct SQLite queries
- v1 codebase at `~/claude_code_projects/icloud-mail-cleanup/lib/envelope_index.py` -- schema knowledge and query patterns
- [Rich 14.3.3 Progress docs](https://rich.readthedocs.io/en/stable/progress.html) -- Progress bar API
- [Rich 14.3.3 Table docs](https://rich.readthedocs.io/en/stable/tables.html) -- Table API

### Secondary (MEDIUM confidence)
- [Rich PyPI page](https://pypi.org/project/rich/) -- version 14.3.3 confirmed
- Scoring model architecture -- based on standard email classification patterns from multiple sources, adapted to this specific dataset

### Tertiary (LOW confidence)
- `flags` field bitmask interpretation -- bit 2 (replied) verified with 96% correlation against conversation-based detection; bit 4 (forwarded) verified by count match. Other bits undocumented.
- `automated_conversation` values (0, 1, 2) -- meanings inferred from names and distributions, not officially documented
- `unsubscribe_type` values -- undocumented; treated as weak signal only

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- stdlib + rich, all verified
- Architecture: HIGH -- all queries empirically tested against live DB
- Pitfalls: HIGH -- discovered and verified through hands-on investigation
- Scoring model: MEDIUM -- architecture is sound but weight tuning needs empirical validation
- Flags bitmask: MEDIUM -- bit 2 verified with 96% correlation, but other bits not fully understood

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable -- Apple Mail schema changes are rare between macOS releases)
