# Phase 2: Content Analysis + Full Classification - Research

**Researched:** 2026-03-05
**Domain:** .emlx parsing, MLX GPU embeddings, semantic clustering, fused classification
**Confidence:** MEDIUM-HIGH

## Summary

Phase 2 adds content analysis to the Phase 1 metadata-only pipeline. It parses ~25K .emlx files from `~/Library/Mail/V10/`, generates embeddings on the M1 Max GPU via mlx-embeddings, clusters emails semantically into ~20-50 coarse groups, and fuses content signals with metadata scores to reclassify ambiguous (Review-tier) emails.

The .emlx format is straightforward -- a byte count line, then a standard RFC 822 message, then an Apple plist. Python's stdlib `email` module handles parsing after extracting the byte count. Real data shows 72% of emails are multipart with text/plain available, 20% are HTML-only (need tag stripping), and 5% are plain-text-only. About 6,269 files are `.partial.emlx` (headers-only, no body) which will fall back to subject-only embedding. File paths use ROWID from the messages table as the filename (e.g., `39493.emlx`), NOT message_id.

For embeddings, `mlx-embeddings` 0.0.5 supports ModernBERT natively and provides `batch_encode_plus` for GPU-accelerated batch processing. The recommended model is `nomic-ai/modernbert-embed-base` (MLX 4-bit quantized at 84MB, 768d embeddings, 8192 token context, Matryoshka support for 256d). This model requires `search_document:` prefix for all texts. For clustering, sklearn's HDBSCAN with cosine metric handles variable-density clusters without needing a target count. TF-IDF over cluster members produces automatic labels.

**Primary recommendation:** Use `mlx-embeddings` with `mlx-community/nomicai-modernbert-embed-base-4bit`, HDBSCAN for clustering, TF-IDF for labeling. Fall back to `all-MiniLM-L6-v2-4bit` if ModernBERT has compatibility issues.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Parse ALL ~25K emails' .emlx files, not just Review tier
- Generate embeddings for every email but only let content signals change classification for Review-tier and borderline cases
- Confident Trash/Keep from Phase 1 remain stable unless content strongly disagrees
- Extract plain text body only -- no MIME header parsing (Envelope Index already has that metadata)
- For HTML-only emails: strip tags and normalize whitespace, no external HTML parsing library
- Coarse clusters (~20-50 groups) -- broad categories like "shipping notifications", "marketing emails", "account alerts"
- Auto-label clusters from content using heuristic keyword extraction (TF-IDF or similar), not Claude API
- No API dependency in Phase 2 -- everything runs locally
- Trash to Keep/Review: YES -- content analysis can promote Trash-classified emails if content shows they're personal/important
- Keep to Trash: NO -- Keep decisions from metadata are final
- Review to any tier: YES -- full flexibility for Review emails
- Review can stay Review if content is still ambiguous
- Single fused confidence score (metadata + content blended), not dual scores
- Walk ~/Library/Mail/V10/ directory tree to build message-ID-to-filepath lookup table
- Missing .emlx files: fall back to subject-only embedding, flag as "subject_only"
- Corrupted/unparseable .emlx: same treatment as missing
- No blocking on parse failures -- processing continues

### Claude's Discretion
- Clustering algorithm choice (DBSCAN, HDBSCAN, agglomerative, etc.)
- MLX embedding model selection (MiniLM, ModernBERT, etc.)
- Body length truncation limit (align with embedding model's context window)
- Exact weight blending between metadata and content signals for fused score
- Batch size and parallelization strategy for GPU embedding

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCAN-04 | Parse .emlx files from disk for email body content extraction | .emlx format fully understood: byte-count header + RFC 822 body + plist. stdlib `email` module parses body. ROWID-based filenames map to messages table. 25,177 files on disk (18,908 full, 6,269 partial). |
| CSIG-03 | Generate MLX embeddings from combined subject+body text using M1 Max GPU | `mlx-embeddings` 0.0.5 supports ModernBERT + BERT. Batch API via `batch_encode_plus`. Model: `nomicai-modernbert-embed-base-4bit` (84MB, 768d, 8192 tokens). Requires `search_document:` prefix. |
| CSIG-04 | Cluster emails semantically across senders | sklearn HDBSCAN with cosine metric. `min_cluster_size` tunable for ~20-50 groups. TF-IDF over cluster members for auto-labeling. Noise points (unclustered) stay as-is. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mlx-embeddings | 0.0.5 | Load and run embedding models on Apple Silicon GPU | Only MLX embedding library with native ModernBERT support; batch API; maintained |
| mlx | >=0.22.0 | Apple Silicon ML framework (dependency of mlx-embeddings) | Required backend for GPU compute |
| scikit-learn | >=1.4 | HDBSCAN clustering + TfidfVectorizer for cluster labeling | HDBSCAN integrated in sklearn since 1.3; no separate hdbscan package needed |
| numpy | >=1.24 | Array operations, embedding matrix handling | MLX arrays convert to numpy for sklearn compatibility |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich | >=14.3 | Progress bars during parsing/embedding/clustering | Already a project dependency from Phase 1 |
| email (stdlib) | - | Parse RFC 822 messages from .emlx files | Core parsing -- no external dependency needed |
| html.parser (stdlib) | - | Strip HTML tags for HTML-only emails | User locked decision: no external HTML library |
| re (stdlib) | - | Whitespace normalization after HTML stripping | Collapse multiple whitespace to single spaces |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| mlx-embeddings | mlx-embedding-models (taylorai) | Simpler API but no ModernBERT support, less maintained, smaller model registry |
| mlx-embeddings | sentence-transformers (CPU) | More mature but CPU-only on macOS, 10-50x slower than GPU for 25K embeddings |
| HDBSCAN | Agglomerative Clustering | Deterministic cluster count but requires specifying k; HDBSCAN finds natural density-based clusters |
| HDBSCAN | KMeans | Faster but requires specifying k and assumes spherical clusters; poor for embedding spaces |
| nomic/modernbert-embed-base | all-MiniLM-L6-v2 | MiniLM is proven stable on MLX but only 512 token context (email bodies can be longer) and lower quality embeddings |

**Installation:**
```bash
uv add mlx-embeddings scikit-learn numpy
```

## Architecture Patterns

### Recommended Project Structure
```
src/icloud_cleanup/
  models.py            # Extended with ContentResult, ClusterInfo dataclasses
  classifier.py        # Extended with fused scoring (metadata + content)
  checkpoint.py        # Extended checkpoint format for content signals
  scanner.py           # Unchanged
  contacts.py          # Unchanged
  display.py           # Extended with content analysis progress
  cli.py               # New 'analyze' subcommand
  emlx_parser.py       # NEW: .emlx file discovery + body extraction
  embedder.py          # NEW: MLX embedding generation (batch)
  clusterer.py         # NEW: HDBSCAN clustering + TF-IDF labeling
```

### Pattern 1: EMLX File Discovery (ROWID-to-Path Lookup)
**What:** Walk the Mail V10 directory tree once, build a dict mapping ROWID to file path
**When to use:** Before any content extraction -- needed to locate .emlx files
**Example:**
```python
# .emlx filenames ARE the ROWID from the messages table
# Path pattern: ~/Library/Mail/V10/{account_uuid}/{mailbox}.mbox/.../Messages/{rowid}.emlx
# Also: {rowid}.partial.emlx for headers-only (no body content)

from pathlib import Path

MAIL_DIR = Path.home() / "Library/Mail/V10"

def build_emlx_lookup(account_uuid: str) -> dict[int, Path]:
    """Walk directory tree, return {ROWID: Path} for all .emlx files."""
    lookup: dict[int, Path] = {}
    account_dir = MAIL_DIR / account_uuid
    for emlx_path in account_dir.rglob("*.emlx"):
        stem = emlx_path.stem  # e.g., "39493" or "39493.partial"
        if ".partial" in stem:
            continue  # Skip partial files -- headers only, no body
        try:
            rowid = int(stem)
            lookup[rowid] = emlx_path
        except ValueError:
            continue
    return lookup
```

### Pattern 2: EMLX Body Extraction
**What:** Parse .emlx file format (byte-count + RFC822 + plist) and extract plain text
**When to use:** For each email that has an .emlx file on disk
**Example:**
```python
import email
import html.parser
import re

class _HTMLStripper(html.parser.HTMLParser):
    """Stdlib-only HTML tag stripper."""
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
    def handle_data(self, data: str) -> None:
        self._parts.append(data)
    def get_text(self) -> str:
        return " ".join(self._parts)

def strip_html(html_text: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html_text)
    text = stripper.get_text()
    return re.sub(r'\s+', ' ', text).strip()

def extract_body(emlx_path: Path, max_chars: int = 4000) -> str | None:
    """Extract plain text body from .emlx file. Returns None on failure."""
    try:
        with open(emlx_path, 'rb') as f:
            bytecount = int(f.readline().strip())
            msg = email.message_from_bytes(f.read(bytecount))

        # Prefer text/plain
        if not msg.is_multipart():
            payload = msg.get_payload(decode=True)
            if payload is None:
                return None
            ct = msg.get_content_type()
            text = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
            if ct == 'text/html':
                text = strip_html(text)
            return text[:max_chars]

        # Multipart: find text/plain first, fall back to text/html
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/plain':
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    return payload.decode(charset, errors='replace')[:max_chars]

        # No text/plain -- try text/html
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    html_text = payload.decode(charset, errors='replace')
                    return strip_html(html_text)[:max_chars]

        return None
    except Exception:
        return None
```

### Pattern 3: Batch MLX Embedding Generation
**What:** Generate embeddings for all emails in GPU-accelerated batches
**When to use:** After body text extraction, before clustering
**Example:**
```python
from mlx_embeddings.utils import load
import mlx.core as mx
import numpy as np

MODEL_ID = "mlx-community/nomicai-modernbert-embed-base-4bit"
PREFIX = "search_document: "
BATCH_SIZE = 64  # Tune based on GPU memory

def embed_texts(texts: list[str], model, tokenizer) -> np.ndarray:
    """Embed a list of texts in batches, return (N, dim) numpy array."""
    all_embeds = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = [PREFIX + t for t in texts[i:i + BATCH_SIZE]]
        inputs = tokenizer.batch_encode_plus(
            batch,
            return_tensors="mlx",
            padding=True,
            truncation=True,
            max_length=512,  # Adjust based on actual token distribution
        )
        outputs = model(
            inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
        )
        # outputs.text_embeds is mean-pooled + normalized
        batch_np = np.array(outputs.text_embeds)
        all_embeds.append(batch_np)
    return np.vstack(all_embeds)
```

### Pattern 4: HDBSCAN Clustering + TF-IDF Labeling
**What:** Cluster embedding vectors into natural groups, label each cluster
**When to use:** After all embeddings are generated
**Example:**
```python
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer

def cluster_embeddings(
    embeddings: np.ndarray,
    min_cluster_size: int = 100,
    min_samples: int = 20,
) -> np.ndarray:
    """Return cluster labels (-1 = noise)."""
    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="cosine",
        cluster_selection_method="eom",  # excess of mass -- finds natural clusters
    )
    return clusterer.fit_predict(embeddings)

def label_clusters(
    texts: list[str],
    labels: np.ndarray,
    top_n: int = 5,
) -> dict[int, list[str]]:
    """Extract top TF-IDF terms per cluster as labels."""
    cluster_ids = sorted(set(labels) - {-1})
    cluster_labels = {}
    for cid in cluster_ids:
        mask = labels == cid
        cluster_texts = [t for t, m in zip(texts, mask) if m]
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=1000,
            max_df=0.9,
        )
        tfidf = vectorizer.fit_transform(cluster_texts)
        feature_names = vectorizer.get_feature_names_out()
        mean_tfidf = tfidf.mean(axis=0).A1
        top_indices = mean_tfidf.argsort()[::-1][:top_n]
        cluster_labels[cid] = [feature_names[i] for i in top_indices]
    return cluster_labels
```

### Pattern 5: Fused Classification (Metadata + Content)
**What:** Blend metadata confidence with content-derived signals for final tier assignment
**When to use:** After clustering, to reclassify Review-tier and borderline emails
**Key insight:** The fused score replaces the original confidence, not supplements it.

```python
# Reclassification rules from CONTEXT.md:
# - Trash -> Keep/Review: YES (safety net)
# - Keep -> Trash: NEVER
# - Review -> any: YES (main target)
# - Review -> Review: allowed (still ambiguous)

METADATA_WEIGHT = 0.6
CONTENT_WEIGHT = 0.4

def fuse_scores(
    metadata_confidence: float,
    content_score: float,
) -> float:
    """Blend metadata and content signals into single confidence."""
    return metadata_confidence * METADATA_WEIGHT + content_score * CONTENT_WEIGHT
```

### Anti-Patterns to Avoid
- **Re-parsing MIME headers from .emlx:** Envelope Index already has sender, subject, date. Don't duplicate this work from .emlx files.
- **Loading all embeddings into memory at once:** 25K x 768d x float32 = ~75MB which IS manageable, but still batch the GPU embedding generation to avoid tokenizer OOM on very long emails.
- **Using message_id to find .emlx files:** The filename is ROWID, not message_id. message_id is a negative hash; ROWID is the positive integer in the filename.
- **Blocking on parse errors:** A single corrupt .emlx should never stop processing 25K emails. Always continue with subject-only fallback.
- **Running HDBSCAN on raw high-dimensional embeddings:** 768d works fine with cosine metric on 25K points. No UMAP/PCA reduction needed at this scale.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML tag stripping | regex-based tag removal | stdlib `html.parser.HTMLParser` subclass | regex fails on malformed HTML, nested tags, CDATA; HTMLParser handles edge cases |
| Email MIME parsing | custom body extractor | stdlib `email.message_from_bytes` + `walk()` | multipart MIME has 30+ edge cases (nested multipart, encodings, charsets) |
| Text embedding | custom word2vec/TF-IDF vectors | mlx-embeddings with pre-trained model | pre-trained models capture semantic meaning; custom vectors would be worse |
| Density-based clustering | custom distance/merge logic | sklearn HDBSCAN | handles noise, variable density, no k parameter; well-tested at scale |
| TF-IDF computation | manual term frequency counting | sklearn TfidfVectorizer | handles stop words, IDF weighting, sparse matrices efficiently |

**Key insight:** The .emlx format and email MIME parsing have enough edge cases (encoding quirks, nested multipart, content-transfer-encoding) that using stdlib's battle-tested `email` module is far safer than custom parsing.

## Common Pitfalls

### Pitfall 1: ROWID vs message_id Confusion
**What goes wrong:** Using message_id (a negative hash like -9204842847840407353) to look up .emlx files instead of ROWID (positive integer like 39493)
**Why it happens:** Phase 1's Classification dataclass stores message_id, and the naming is confusing
**How to avoid:** The lookup table must map ROWID to filepath. Messages already have `.rowid` attribute from Phase 1. Use that.
**Warning signs:** No .emlx files found, or all lookups returning None

### Pitfall 2: Partial .emlx Files Have No Body
**What goes wrong:** Trying to parse body content from `.partial.emlx` files and getting empty/corrupt results
**Why it happens:** Apple Mail downloads headers first; body comes later. 6,269 files (25%) are partial.
**How to avoid:** Skip `.partial.emlx` in the lookup table build. These ROWIDs get subject-only embedding.
**Warning signs:** High parse failure rate, empty body text

### Pitfall 3: Character Encoding Chaos
**What goes wrong:** UnicodeDecodeError or garbled text from email bodies
**Why it happens:** Emails span 2011-2026 with varied charsets (utf-8, latin-1, windows-1252, iso-2022-jp, etc.)
**How to avoid:** Always use `errors='replace'` when decoding. Use `part.get_content_charset()` with fallback to utf-8. Never assume encoding.
**Warning signs:** Mojibake in extracted text, decode exceptions

### Pitfall 4: MLX Tokenizer Memory on Long Emails
**What goes wrong:** Memory spike when tokenizing very long email bodies in a single batch
**Why it happens:** Marketing emails can be 50K+ characters. Padding to max length in a batch wastes memory.
**How to avoid:** Truncate body text BEFORE tokenization (e.g., 4000 chars). The model's 8192 token limit means ~4000 English chars is a safe ceiling. Also batch in groups of 64, not all 25K at once.
**Warning signs:** System memory pressure, MLX OOM

### Pitfall 5: HDBSCAN Noise Label (-1) Domination
**What goes wrong:** HDBSCAN labels most points as noise, producing very few clusters
**Why it happens:** min_cluster_size or min_samples set too high for the data distribution; embedding space may be sparse
**How to avoid:** Start with `min_cluster_size=100, min_samples=20`. If >40% noise, lower min_cluster_size. Test on the actual embeddings -- email embedding distributions vary.
**Warning signs:** Cluster count < 10, noise fraction > 50%

### Pitfall 6: Checkpoint Format Breaking Change
**What goes wrong:** Phase 2 checkpoint is incompatible with Phase 1 or Phase 3
**Why it happens:** Adding content signals, cluster IDs, and fused scores to the Classification dataclass
**How to avoid:** Extend Classification with optional fields (content_score, cluster_id, cluster_label). Keep backward compatibility -- Phase 1 checkpoints still load. Use `merge_checkpoint` to overlay Phase 2 results.
**Warning signs:** KeyError on checkpoint load, schema mismatch

### Pitfall 7: nomic-ai Model Requires Prefix
**What goes wrong:** Poor embedding quality, low clustering coherence
**Why it happens:** The nomic/modernbert-embed model is trained with task prefixes. Omitting `search_document:` degrades quality significantly.
**How to avoid:** Always prepend `search_document: ` to every text before tokenization.
**Warning signs:** All emails cluster into a single blob, or clusters don't make semantic sense

## Code Examples

### Complete EMLX Body Extraction with Error Handling
```python
# Source: verified against actual .emlx files in ~/Library/Mail/V10/
# on this machine (2026-03-05)

import email
import html.parser
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

class _HTMLStripper(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        return re.sub(r'\s+', ' ', raw).strip()


def strip_html(html_text: str) -> str:
    stripper = _HTMLStripper()
    try:
        stripper.feed(html_text)
    except Exception:
        # Fallback: crude regex strip for severely malformed HTML
        return re.sub(r'<[^>]+>', ' ', html_text)
    return stripper.get_text()


def parse_emlx_body(path: Path, max_chars: int = 4000) -> str | None:
    """Extract plain text body from .emlx file.

    Returns None if file is unparseable or has no text content.
    Truncates to max_chars to align with embedding model context window.
    """
    try:
        with open(path, 'rb') as f:
            bytecount = int(f.readline().strip())
            msg_bytes = f.read(bytecount)
        msg = email.message_from_bytes(msg_bytes)
    except Exception as exc:
        log.warning("Failed to parse %s: %s", path.name, exc)
        return None

    # Non-multipart
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if not payload:
            return None
        charset = msg.get_content_charset() or 'utf-8'
        text = payload.decode(charset, errors='replace')
        if msg.get_content_type() == 'text/html':
            text = strip_html(text)
        return text[:max_chars] if text.strip() else None

    # Multipart: prefer text/plain
    for part in msg.walk():
        if part.get_content_type() == 'text/plain':
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or 'utf-8'
                text = payload.decode(charset, errors='replace')
                if text.strip():
                    return text[:max_chars]

    # Fallback: text/html
    for part in msg.walk():
        if part.get_content_type() == 'text/html':
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or 'utf-8'
                html_text = payload.decode(charset, errors='replace')
                text = strip_html(html_text)
                if text.strip():
                    return text[:max_chars]

    return None
```

### MLX Embedding with Fallback Model
```python
# Source: mlx-embeddings README + mlx-community HuggingFace model cards

from mlx_embeddings.utils import load
import mlx.core as mx
import numpy as np

PRIMARY_MODEL = "mlx-community/nomicai-modernbert-embed-base-4bit"
FALLBACK_MODEL = "mlx-community/all-MiniLM-L6-v2-4bit"
DOC_PREFIX = "search_document: "

def load_embedding_model():
    """Load ModernBERT, fall back to MiniLM on failure."""
    try:
        model, tokenizer = load(PRIMARY_MODEL)
        return model, tokenizer, PRIMARY_MODEL
    except Exception as exc:
        log.warning("ModernBERT load failed (%s), falling back to MiniLM", exc)
        model, tokenizer = load(FALLBACK_MODEL)
        return model, tokenizer, FALLBACK_MODEL

def batch_embed(
    texts: list[str],
    model,
    tokenizer,
    model_name: str,
    batch_size: int = 64,
    max_length: int = 512,
) -> np.ndarray:
    """Generate embeddings in GPU batches. Returns (N, dim) numpy array."""
    prefix = DOC_PREFIX if "modernbert" in model_name else ""
    all_embeds = []
    for i in range(0, len(texts), batch_size):
        batch = [prefix + t for t in texts[i:i + batch_size]]
        inputs = tokenizer.batch_encode_plus(
            batch,
            return_tensors="mlx",
            padding=True,
            truncation=True,
            max_length=max_length,
        )
        outputs = model(
            inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
        )
        # Force GPU computation to complete before converting to numpy
        mx.eval(outputs.text_embeds)
        batch_np = np.array(outputs.text_embeds)
        all_embeds.append(batch_np)
    return np.vstack(all_embeds)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| all-MiniLM-L6-v2 (512 tokens) | ModernBERT-embed-base (8192 tokens) | Dec 2024 | 16x longer context, better MTEB scores, modern architecture |
| sentence-transformers (CPU) | mlx-embeddings (GPU) | 2024 | Native Apple Silicon GPU acceleration, 10-50x faster |
| standalone hdbscan package | sklearn.cluster.HDBSCAN | sklearn 1.3 (2023) | No separate install, same algorithm, integrated with sklearn ecosystem |
| Fixed k-means clustering | HDBSCAN density-based | - | No need to specify cluster count, handles noise naturally |
| TF-IDF for embeddings | Transformer embeddings + TF-IDF for labeling only | - | Embeddings capture semantics; TF-IDF still best for readable cluster labels |

**Deprecated/outdated:**
- `hdbscan` standalone package: use `sklearn.cluster.HDBSCAN` instead (integrated since sklearn 1.3)
- `plistlib.readPlistFromBytes()`: use `plistlib.loads()` (Python 3.4+)
- all-MiniLM-L6-v2 for new projects: outdated architecture, short context. Still works as fallback.

## Open Questions

1. **mlx-embeddings 0.0.5 batch API stability**
   - What we know: README shows `batch_encode_plus` working with MLX tensors. ModernBERT architecture is listed as supported.
   - What's unclear: Whether the 4-bit quantized ModernBERT model works correctly with `batch_encode_plus` in practice. The library is at 0.0.5 (pre-1.0).
   - Recommendation: Include a validation step in the first plan task that loads the model, embeds 10 test texts, and verifies output shapes/similarity scores. If it fails, switch to MiniLM fallback immediately.

2. **Optimal batch size for M1 Max 32-core GPU**
   - What we know: M1 Max has 32 GPU cores and unified memory. MLX should saturate the GPU.
   - What's unclear: Whether batch_size=64 or 128 or 256 is optimal for ModernBERT 4-bit on this specific hardware.
   - Recommendation: Start with 64, measure throughput, and tune. Not blocking -- any reasonable batch size works.

3. **HDBSCAN parameter tuning for email embeddings**
   - What we know: min_cluster_size=100 and min_samples=20 are reasonable starting points for 25K documents.
   - What's unclear: The actual cluster distribution from real email embeddings. May need adjustment.
   - Recommendation: Add a tuning step that tries 2-3 parameter sets and picks the one closest to 20-50 clusters with <40% noise.

4. **Content score derivation from clusters**
   - What we know: Cluster membership is the primary content signal. Emails in a "shipping notifications" cluster should score low (trash-worthy). Emails in a "personal correspondence" cluster should score high.
   - What's unclear: Exact mapping from cluster identity to a 0-1 content score.
   - Recommendation: Use cluster composition analysis -- if a cluster is dominated by Phase 1 Trash-tier emails, assign low content scores. If dominated by Keep-tier, assign high. Mixed clusters get mid-range.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCAN-04 | Parse .emlx body content from byte-count + RFC822 format | unit | `uv run pytest tests/test_emlx_parser.py -x` | Wave 0 |
| SCAN-04 | Handle missing/corrupt/partial .emlx gracefully | unit | `uv run pytest tests/test_emlx_parser.py::TestErrorHandling -x` | Wave 0 |
| SCAN-04 | Build ROWID-to-filepath lookup table | unit | `uv run pytest tests/test_emlx_parser.py::TestLookupTable -x` | Wave 0 |
| SCAN-04 | Strip HTML from HTML-only emails | unit | `uv run pytest tests/test_emlx_parser.py::TestHtmlStripping -x` | Wave 0 |
| CSIG-03 | Generate embeddings from text using MLX model | unit/integration | `uv run pytest tests/test_embedder.py -x` | Wave 0 |
| CSIG-03 | Batch processing produces correct output shapes | unit | `uv run pytest tests/test_embedder.py::TestBatchEmbed -x` | Wave 0 |
| CSIG-03 | Subject-only fallback for missing bodies | unit | `uv run pytest tests/test_embedder.py::TestFallback -x` | Wave 0 |
| CSIG-04 | HDBSCAN clustering produces 20-50 clusters | integration | `uv run pytest tests/test_clusterer.py::TestClustering -x` | Wave 0 |
| CSIG-04 | TF-IDF cluster labeling produces readable labels | unit | `uv run pytest tests/test_clusterer.py::TestLabeling -x` | Wave 0 |
| CSIG-04 | Fused score reclassifies Review emails correctly | unit | `uv run pytest tests/test_classifier.py::TestFusedClassification -x` | Wave 0 |
| CSIG-04 | Reclassification respects locked tier rules | unit | `uv run pytest tests/test_classifier.py::TestReclassRules -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_emlx_parser.py` -- covers SCAN-04 (parsing, lookup, HTML stripping, error handling)
- [ ] `tests/test_embedder.py` -- covers CSIG-03 (embedding generation, batch, fallback)
- [ ] `tests/test_clusterer.py` -- covers CSIG-04 (clustering, labeling)
- [ ] Extended `tests/test_classifier.py` -- covers fused scoring and reclassification rules
- [ ] Dependencies installed: `uv add mlx-embeddings scikit-learn numpy`

## Sources

### Primary (HIGH confidence)
- Actual filesystem inspection: `~/Library/Mail/V10/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/` -- 25,177 .emlx files, 18,908 full, 6,269 partial. ROWID-based filenames verified against Envelope Index SQLite.
- Live .emlx parsing test: Python stdlib `email.message_from_bytes` successfully parsed real files. Content type distribution: 72% multipart with text/plain, 20% HTML-only, 5% text-only, 3.6% multipart without text/plain.
- [mlx-embeddings PyPI](https://pypi.org/project/mlx-embeddings/) -- v0.0.5, released 2025-10-29
- [mlx-embeddings GitHub README](https://github.com/Blaizzy/mlx-embeddings) -- API: load(), batch_encode_plus, model() -> outputs.text_embeds
- [nomic-ai/modernbert-embed-base HuggingFace](https://huggingface.co/nomic-ai/modernbert-embed-base) -- 768d, 8192 tokens, Matryoshka 256d, requires search_document: prefix
- [mlx-community/nomicai-modernbert-embed-base-4bit HuggingFace](https://huggingface.co/mlx-community/nomicai-modernbert-embed-base-4bit) -- 84MB quantized, Apache 2.0
- [sklearn HDBSCAN docs](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html) -- sklearn 1.8, cosine metric supported
- [EMLX format spec](https://docs.fileformat.com/email/emlx/) -- byte count + RFC822 + plist structure
- [Python email.parser docs](https://docs.python.org/3/library/email.parser.html) -- message_from_bytes, get_body, walk()

### Secondary (MEDIUM confidence)
- [HDBSCAN parameter selection guide](https://hdbscan.readthedocs.io/en/latest/parameter_selection.html) -- min_cluster_size tuning guidance
- [HN discussion on embedding models](https://news.ycombinator.com/item?id=46081800) -- nomic-embed and modernbert recommended over MiniLM
- [EMLX parsing gist](https://gist.github.com/karlcow/5276813) -- Python parsing pattern confirmed

### Tertiary (LOW confidence)
- Batch size 64 recommendation: based on general MLX experience, not benchmarked on this specific model+hardware. Needs empirical validation.
- HDBSCAN min_cluster_size=100 starting point: reasonable heuristic for 25K documents, but actual email embedding distribution may require different values.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- mlx-embeddings, sklearn HDBSCAN are well-documented; API verified from official sources
- Architecture (.emlx parsing): HIGH -- verified against actual files on this machine; format is simple and well-understood
- Architecture (embedding pipeline): MEDIUM -- mlx-embeddings 0.0.5 is pre-1.0; batch API and ModernBERT support confirmed in docs but not locally tested
- Pitfalls: HIGH -- ROWID vs message_id verified empirically; partial.emlx count verified; content type distribution measured
- Clustering parameters: MEDIUM -- good starting points but need empirical tuning on actual embeddings

**Research date:** 2026-03-05
**Valid until:** 2026-04-05 (stable domain; mlx-embeddings may release new versions)
