# Architecture Patterns

**Domain:** On-device email classification and cleanup pipeline
**Researched:** 2026-03-04

## Recommended Architecture

A five-layer pipeline architecture with clear data flow boundaries. Each layer produces an artifact that the next layer consumes, enabling independent testing, caching, and incremental re-runs.

```
Layer 1: Data Extraction
  Envelope Index SQLite (read-only) + .emlx files on disk
    |
    v
Layer 2: Feature Engineering (3 parallel signal extractors)
  [Contact Reputation] [Content Embeddings] [Behavioral Signals]
    \                    |                    /
     \                   |                   /
      v                  v                  v
Layer 3: Score Fusion & Classification
  Weighted combination -> 4-tier classification -> confidence score
    |
    v
Layer 4: Report & Review
  Structured report generation -> interactive terminal review
    |
    v
Layer 5: Safe Execution
  Approved actions -> AppleScript batch mover -> verification
```

### Component Boundaries

| Component | Responsibility | Inputs | Outputs | Communicates With |
|-|-|-|-|-|
| `EnvelopeReader` | Read-only SQLite queries against Envelope Index | DB path, account UUID | `list[EmailRecord]` with metadata + flags | Feature extractors |
| `EmlxExtractor` | Parse .emlx files for body text and attachments | Mailbox paths from EnvelopeReader | `dict[message_id, EmailContent]` (plain text, HTML stripped) | ContentEmbedder |
| `ContactScorer` | Build sender reputation from reply history, frequency, contacts DB | `list[EmailRecord]`, career DB path | `dict[sender, ContactScore]` | ScoreFusion |
| `ContentEmbedder` | Generate embeddings via MLX, cluster by semantic similarity | `dict[message_id, EmailContent]` | `dict[message_id, np.ndarray]` + cluster labels | ScoreFusion |
| `BehaviorAnalyzer` | Extract read/replied/forwarded/ignored/deleted patterns from flags | `list[EmailRecord]` (flags column) | `dict[sender, BehaviorScore]` | ScoreFusion |
| `ScoreFusion` | Combine 3 signal scores into final classification + confidence | All three scorer outputs | `list[ClassifiedEmail]` with tier + confidence | ReportGenerator |
| `ReportGenerator` | Produce JSON + Markdown grouped report | `list[ClassifiedEmail]` | Files on disk | InteractiveReview |
| `InteractiveReview` | Terminal UI for approving/rejecting categories | Report JSON | Modified report with user decisions | SafeExecutor |
| `SafeExecutor` | Batch-move approved emails to Trash via AppleScript | Approved message IDs | Execution log, verification counts | None (terminal) |

### Data Flow

**Phase 1 -- Extraction (sequential, I/O-bound):**
1. `EnvelopeReader` opens Envelope Index in read-only mode (URI `?mode=ro` to avoid WAL locks while Mail.app runs).
2. Single query fetches all iCloud messages with JOINs to addresses, subjects, mailboxes, message_global_data.
3. Result: in-memory list of `EmailRecord` dataclasses with all metadata including flags bitmap.
4. `EmlxExtractor` resolves `.emlx` file paths from mailbox structure under `~/Library/Mail/V10/`. Parses each file: reads byte count header, extracts MIME body via Python `email` stdlib, strips HTML to plain text. Operates in parallel (6-8 workers via `ProcessPoolExecutor`).

**Phase 2 -- Feature Engineering (parallel, CPU/GPU-bound):**
Three scorers run independently and can execute concurrently:

5. `ContactScorer` builds a sender graph from the full message list:
   - Counts emails sent vs received per address
   - Detects reply chains (answered flag in bitmap)
   - Checks against career engine contacts DB for known-person boost
   - Checks for no-reply/automated sender patterns
   - Output: float score per sender (0.0 = pure spam, 1.0 = close contact)

6. `ContentEmbedder` processes email bodies through MLX:
   - Batches texts (128-256 per batch, respecting token limits)
   - Generates embeddings using `mlx-embeddings` with a lightweight model (all-MiniLM-L6-v2 or nomic-embed-text-v1.5)
   - Runs HDBSCAN or k-means clustering on embeddings to identify content groups
   - Computes per-email "spam-likeness" by distance to known-spam cluster centroids
   - Output: embedding vector + cluster label + spam-distance per message

7. `BehaviorAnalyzer` decodes the flags bitmap from the messages table:
   - Bit 0: read, Bit 2: answered/replied, Bit 4: flagged, Bit 8: forwarded
   - Aggregates per-sender: % read, % replied, % flagged, % ignored (unread + old)
   - Computes engagement score: replies and flags weight heavily, reads moderately, ignores negatively
   - Output: float score per sender (0.0 = always ignored, 1.0 = always engaged)

**Phase 3 -- Fusion (CPU-bound, fast):**
8. `ScoreFusion` combines the three signals using weighted linear combination:
   ```
   final_score = w_contact * contact_score + w_content * content_score + w_behavior * behavior_score
   ```
   Default weights: contact=0.35, content=0.40, behavior=0.25
   (Content gets highest weight because it directly indicates value; contact is strong but can miss new senders; behavior is noisy for old/bulk emails.)

9. Score-to-tier mapping with confidence:
   - Trash: final_score < 0.25 AND confidence > 0.7
   - Keep-Active: final_score > 0.70
   - Keep-Historical: 0.50 < final_score < 0.70 AND age > 2 years
   - Review: everything else (ambiguous zone or low confidence)

10. Confidence = agreement between signals. When all three signals agree (all high or all low), confidence is high. When signals disagree (e.g., unknown sender but engaged content), confidence drops, forcing the email into Review tier.

**Phase 4 -- Report & Review (I/O-bound):**
11. `ReportGenerator` produces:
    - JSON with full classification data (machine-readable, for re-processing)
    - Markdown summary grouped by tier, then by sender cluster (human-readable)
    - Statistics dashboard: confidence distribution, tier breakdown, signal disagreement highlights

12. `InteractiveReview` presents a terminal walkthrough:
    - Shows Review-tier groups one at a time with context (sender, subjects, signal scores)
    - User approves (keep/trash) or defers each group
    - Updates the report JSON with decisions

**Phase 5 -- Execution (I/O-bound, rate-limited):**
13. `SafeExecutor` reads approved-trash decisions from report JSON
    - Groups messages by source mailbox
    - Batches AppleScript calls (50-100 messages per batch)
    - Moves to "Deleted Messages" (not permanent delete)
    - Logs every action with message ID, subject snippet, sender
    - Verification pass: re-queries Envelope Index to confirm moves

## Patterns to Follow

### Pattern 1: Dataclass-Based Pipeline Records
**What:** Every pipeline stage operates on typed dataclasses. No raw dicts flowing between components.
**When:** Always. This is the fundamental contract between components.
**Why:** Type hints catch integration bugs at development time. Dataclasses are lightweight and serialize cleanly.
```python
from dataclasses import dataclass, field

@dataclass
class EmailRecord:
    """Raw extraction from Envelope Index."""
    rowid: int
    message_id: int
    sender: str
    subject: str
    date_received: int | None
    mailbox_url: str
    flags: int  # bitmap
    size: int

    @property
    def is_read(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def is_replied(self) -> bool:
        return bool(self.flags & 0x04)

    @property
    def is_flagged(self) -> bool:
        return bool(self.flags & 0x10)

    @property
    def is_forwarded(self) -> bool:
        return bool(self.flags & 0x100)


@dataclass
class SignalScores:
    """Combined scores from all three signal extractors."""
    contact: float  # 0.0-1.0
    content: float  # 0.0-1.0
    behavior: float  # 0.0-1.0

    @property
    def agreement(self) -> float:
        """How much the three signals agree (low variance = high agreement)."""
        scores = [self.contact, self.content, self.behavior]
        mean = sum(scores) / 3
        variance = sum((s - mean) ** 2 for s in scores) / 3
        return 1.0 - min(variance * 4, 1.0)  # scale to 0-1


@dataclass
class ClassifiedEmail:
    """Final classification output."""
    record: EmailRecord
    signals: SignalScores
    tier: str  # "trash" | "keep-active" | "keep-historical" | "review"
    confidence: float  # 0.0-1.0
    reasons: list[str] = field(default_factory=list)
```

### Pattern 2: Cache-First Processing with JSON Checkpoints
**What:** Each expensive pipeline stage writes its output to a JSON checkpoint file. On re-run, skip stages whose checkpoint exists and input hasn't changed.
**When:** For extraction, embedding generation, and scoring stages -- any step that takes more than a few seconds.
**Why:** 25,000+ emails take significant time to embed. Iterating on scoring weights or classification thresholds should not require re-embedding.
```python
CACHE_DIR = Path(".cache")

def load_or_compute(cache_key: str, compute_fn, *args):
    cache_path = CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    result = compute_fn(*args)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, default=str))
    return result
```

### Pattern 3: Batch-Then-Score (Not Stream)
**What:** Load all data first, then process in bulk. Do not stream through the pipeline one email at a time.
**When:** Always for this scale (25K is small enough to hold in memory, large enough that per-item overhead matters).
**Why:** Sender reputation requires global context (need all emails from a sender to compute frequency). Embeddings batch efficiently on GPU (128+ at a time). Clustering requires the full embedding matrix. The entire dataset fits comfortably in memory (~25K records * ~2KB each = ~50MB for metadata, ~1GB for embeddings at 384 dimensions float32).

### Pattern 4: Parallel .emlx Extraction with ProcessPoolExecutor
**What:** Parse .emlx files using a process pool, not sequentially.
**When:** During content extraction (Phase 1).
**Why:** .emlx parsing is I/O-bound (reading 25K files from disk) with some CPU work (MIME parsing, HTML stripping). 6 workers on M1 Max saturates the I/O subsystem without thrashing. Previous project proved 6-worker parallelism gives ~26x speedup on similar file-scanning workloads.
```python
from concurrent.futures import ProcessPoolExecutor

def extract_all_emlx(paths: list[Path], max_workers: int = 6) -> dict[int, str]:
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(parse_single_emlx, paths, chunksize=100)
    return {msg_id: text for msg_id, text in results if text}
```

### Pattern 5: Defensive Scoring with Floor/Ceiling Guards
**What:** Every scorer outputs a normalized 0.0-1.0 float. Unknown/missing data gets a neutral 0.5 score, not 0.0.
**When:** Always in the scoring layer.
**Why:** Missing data should push emails to Review, not to Trash. A sender we've never seen before isn't spam -- they're unknown. Defaulting unknowns to 0.5 means the other two signals drive the decision, and if those also lack data, the email lands in Review (which is correct).

## Anti-Patterns to Avoid

### Anti-Pattern 1: Apple Mail Categories as Ground Truth
**What:** Using `model_category` from `message_global_data` as a classification input or training label.
**Why bad:** The entire motivation for this project is that Apple's categories are unreliable. 36% of emails have no category. Primary/Promotions/Transactions boundaries are inconsistent. Using them as input creates circular dependency on the system you're replacing.
**Instead:** Ignore `model_category` entirely. Build classification from first principles using contact, content, and behavioral signals.

### Anti-Pattern 2: Single-Signal Classification
**What:** Classifying emails based solely on sender pattern matching (e.g., "noreply@ = trash").
**Why bad:** v1 did this and produced poor results. Many legitimate services use noreply@ addresses (bank alerts, flight confirmations, event tickets). Pattern matching alone has high false-positive rates for important transactional emails.
**Instead:** Use sender patterns as one signal (ContactScorer) combined with content analysis and behavioral history. A noreply@ sender whose emails you always read should score higher than one you always ignore.

### Anti-Pattern 3: Embedding Everything
**What:** Running MLX embeddings on all 25K emails including those already clearly classifiable.
**Why bad:** Many emails can be classified with high confidence from metadata alone (known contacts, obvious spam senders, already-in-junk). Embedding is the most expensive step. Running it on emails that don't need it wastes GPU time.
**Instead:** Use a two-pass approach: (1) classify easy cases with metadata-only signals, (2) run embeddings only on ambiguous cases (~5K-10K emails likely need content analysis). This cuts embedding time by 50-75%.

### Anti-Pattern 4: Permanent Deletion
**What:** Calling `delete` instead of moving to Trash via AppleScript.
**Why bad:** One false positive destroys an irreplaceable email. Moving to Trash is reversible. Users can review Trash before permanent deletion happens (Mail.app auto-purges after 30 days by default, configurable).
**Instead:** Always move to "Deleted Messages" mailbox. Never call `delete` on message objects. Log every action for audit.

### Anti-Pattern 5: Modifying the Envelope Index
**What:** Writing to the SQLite database to update flags, categories, or delete records.
**Why bad:** The Envelope Index is owned by Mail.app. Writing to it while Mail.app is running causes corruption, WAL conflicts, and data loss. Mail.app may overwrite your changes on next sync.
**Instead:** Read-only access always (URI `?mode=ro`). All mutations go through AppleScript, which uses Mail.app's own APIs.

## Key Architecture Decisions

### EMLX Path Resolution
Apple Mail stores .emlx files in a nested structure under `~/Library/Mail/V10/`:
```
~/Library/Mail/V10/
  {account-uuid}/
    {mailbox}.mbox/
      Data/
        {0-9}/
          {0-9}/
            Messages/
              {message-id}.emlx
```
The mapping from Envelope Index message to .emlx file path requires:
1. Account UUID (known: `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`)
2. Mailbox folder name (derivable from `mailboxes.url`)
3. Message file naming convention (typically uses the message ROWID from the messages table)

Build a path resolver that walks the directory tree once and builds an index (`dict[int, Path]`) mapping message ROWIDs to .emlx paths. This avoids repeated filesystem traversal.

### Two-Pass Classification Strategy
```
Pass 1: Metadata-only (fast, no GPU)
  - Known contacts -> Keep-Active (HIGH confidence)
  - Reply/forward history -> Keep (HIGH confidence)
  - Known spam senders (5+ emails, never read) -> Trash (HIGH confidence)
  - Already in Junk/Deleted -> Trash (HIGH confidence)
  - Remaining: ~5K-10K emails need content analysis

Pass 2: Content + full scoring (GPU-accelerated)
  - Extract .emlx content for ambiguous emails only
  - Generate MLX embeddings in batches of 128-256
  - Cluster and compute content scores
  - Run full 3-signal fusion
  - Classify remaining emails with confidence scores
```
This two-pass approach is not about skipping signals -- it's about using the cheapest signals first to reduce the expensive work.

### Claude API for Edge Cases (Optional, User-Gated)
For the lowest-confidence Review-tier emails (bottom 5%), optionally send email content to Claude API for a natural language classification judgment. This is:
- Opt-in only (user must explicitly enable with a flag)
- Rate-limited (max 50-100 API calls per run)
- Logged (every API call recorded with input/output)
- Only used for emails where all three signals disagree AND confidence < 0.3

### Embedding Model Selection
Use `all-MiniLM-L6-v2` (384 dimensions) via `mlx-embeddings` as the default. Rationale:
- Smallest model that produces high-quality semantic embeddings
- 384-dim vectors keep memory manageable: 25K * 384 * 4 bytes = ~37MB
- Well-tested on MLX, available as 4-bit quantized (`mlx-community/all-MiniLM-L6-v2-4bit`)
- Email text is short-form (subjects + first few hundred words of body), doesn't need large-context models
- If quality is insufficient, upgrade path: `nomic-embed-text-v1.5` (768 dims, Matryoshka support for variable dimensions)

## Scalability Considerations

| Concern | At 25K emails (current) | At 100K emails | At 500K+ emails |
|-|-|-|-|
| Metadata extraction | ~2 seconds, single query | ~8 seconds, still single query | Paginate query, stream results |
| .emlx parsing | ~30 seconds (6 workers) | ~2 minutes (6 workers) | Add worker count, consider async I/O |
| MLX embedding | ~5 min for 10K texts (batch 128) | ~20 min for 40K texts | Two-pass filtering critical; consider chunked processing with progress bar |
| Memory (metadata) | ~50MB | ~200MB | Fine, M1 Max has 32-64GB unified |
| Memory (embeddings) | ~37MB (384-dim, 25K) | ~150MB | Fine |
| Clustering | < 1 second (HDBSCAN on 25K) | ~5 seconds | Switch to mini-batch k-means |
| AppleScript execution | ~5 min for 1K deletes | ~20 min | Larger batch sizes (200+), longer rate limit pauses |

## Module/File Layout

```
icloud-mail-cleanup-v2/
  lib/
    envelope_reader.py    # EnvelopeReader: SQLite queries, EmailRecord dataclass
    emlx_extractor.py     # EmlxExtractor: .emlx parsing, path resolution, parallel I/O
    contact_scorer.py     # ContactScorer: sender reputation, contact graph
    content_embedder.py   # ContentEmbedder: MLX embeddings, clustering
    behavior_analyzer.py  # BehaviorAnalyzer: flags decoding, engagement scoring
    score_fusion.py       # ScoreFusion: weighted combination, tier assignment, confidence
    report_generator.py   # ReportGenerator: JSON + Markdown output
  scripts/
    classify.py           # CLI entry point: --scan, --report, --review, --execute
  .cache/                 # Checkpoint files (gitignored)
  seeds/                  # Generated reports
```

## Suggested Build Order

Based on dependencies between components:

1. **EnvelopeReader** (no dependencies) -- foundation for everything else
2. **BehaviorAnalyzer** (depends on EnvelopeReader) -- simplest scorer, validates flags bitmap decoding
3. **ContactScorer** (depends on EnvelopeReader) -- metadata-only scoring, can classify ~60% of emails
4. **EmlxExtractor** (depends on EnvelopeReader for path mapping) -- enables content analysis
5. **ContentEmbedder** (depends on EmlxExtractor) -- most complex component, needs MLX setup
6. **ScoreFusion** (depends on all three scorers) -- integration point, needs tuning
7. **ReportGenerator** (depends on ScoreFusion) -- output formatting
8. **InteractiveReview** (depends on ReportGenerator) -- UX polish
9. **SafeExecutor** (depends on InteractiveReview) -- carry forward from v1 with improvements

The first three components (EnvelopeReader + BehaviorAnalyzer + ContactScorer) deliver a working metadata-only classifier that can classify most emails without any GPU work. This is a strong MVP milestone before adding the more complex content embedding pipeline.

## Sources

- [EMLX file format parser](https://github.com/mikez/emlx)
- [MLX-Embeddings library](https://github.com/Blaizzy/mlx-embeddings)
- [Qwen3 MLX embedding server (batch processing patterns)](https://github.com/jakedahn/qwen3-embeddings-mlx)
- [Mail.app Database Schema](https://labs.wordtothewise.com/mailapp/)
- [Envelope Index query patterns](https://gist.github.com/sughodke/1f198a2efe8dd7418fdaa57f003baea7)
- [Apple Mail EMLX format analysis](https://www.loc.gov/preservation/digital/formats//fdd/fdd000615.shtml)
- [Confidence calibration for multi-class classifiers](https://arxiv.org/abs/2411.02988)
- [Score fusion with weighted classifiers](https://link.springer.com/chapter/10.1007/978-981-16-8976-5_6)
- [EMMA multimodal email classification architecture](https://www.mdpi.com/2078-2489/14/12/661)
- [Supervised ML methods for email classification survey (2025)](https://www.tandfonline.com/doi/full/10.1080/21642583.2025.2474450)
- [Token-count batching for embedding inference](https://www.mongodb.com/company/blog/engineering/token-count-based-batching-faster-cheaper-embedding-inference-for-queries)
