# Technology Stack

**Project:** iCloud Mail Cleanup v2
**Researched:** 2026-03-04
**Overall Confidence:** MEDIUM-HIGH (core stack verified; MLX embedding libraries are early-stage and need version pinning at install time)

## Recommended Stack

### Runtime & Package Management

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| Python | 3.13.x (installed: 3.13.7) | Runtime | Already on the machine. MLX 0.31.0 ships wheels for 3.13. If mlx-embeddings has issues, pin to 3.12 in a uv venv. | HIGH |
| uv | latest | Package/venv manager | Javi's preferred tool. Rust-based, 10-100x faster than pip. Manages pyproject.toml, lockfile, and venvs natively. | HIGH |

### Core Framework

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| sqlite3 (stdlib) | built-in | Envelope Index DB access | Zero deps. Python's sqlite3 module with URI mode (`?mode=ro`) for safe read-only access while Mail.app runs. v1 proved this works perfectly. No ORM needed -- raw SQL with `Row` factory is simpler for a read-only analytics workload. | HIGH |
| pathlib (stdlib) | built-in | File path handling | Javi's preference over os.path. Required for traversing `~/Library/Mail/V10/` tree to find .emlx files by message ID. | HIGH |
| email (stdlib) | built-in | MIME parsing | The `emlx` library delegates to this internally. For direct .emlx parsing, this handles headers, multipart bodies, and content type detection without any external dependency. | HIGH |

### Email Parsing

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| emlx | 1.0.4 | .emlx file parser | Lightweight wrapper around stdlib `email`. Handles the Apple-specific bytecount prefix and plist suffix that raw email parsing misses. Extends `email.message.Message` so all standard email methods work. Last updated 2020 but the .emlx format hasn't changed since 2005 -- stability is a feature here. | HIGH |
| beautifulsoup4 | 4.14.x | HTML email to text | Many emails are HTML-only. BS4 with `html.parser` (stdlib, no lxml needed) strips tags to extract text for embedding. `.get_text(separator=' ', strip=True)` is the one-liner. | HIGH |

### ML / Embeddings

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| mlx | >=0.22.0 | Apple Silicon ML array framework | Apple's own framework. Unified memory means no CPU-GPU copies. 32-core GPU on M1 Max makes local inference fast and free. The project constraint. | HIGH |
| mlx-embeddings | >=0.0.5 | Embedding model runner | Supports BERT, XLM-RoBERTa, and ModernBERT architectures via MLX. More actively maintained than mlx-embedding-models (last release Oct 2025). Supports batch processing. Handles model download and caching from HuggingFace hub automatically. | MEDIUM |
| numpy | latest | Vector math | Cosine similarity, normalization, batch operations on embedding vectors. MLX arrays can be converted to numpy for similarity computations. Lightweight, already a transitive dep of mlx. | HIGH |

**Recommended Embedding Model:** `nomic-ai/modernbert-embed-base`
- ModernBERT architecture (2024-2025) outperforms the legacy all-MiniLM-L6-v2 on quality benchmarks
- Supports Matryoshka dimensions (256 dim = 3x memory savings with minimal quality loss -- ideal for 25K emails)
- 8192 token context length (vs 512 for MiniLM) -- handles long emails without truncation
- Confidence: MEDIUM (not yet tested locally -- validate at phase start)

**Fallback Model:** `sentence-transformers/all-MiniLM-L6-v2` (via mlx-community/all-MiniLM-L6-v2 MLX conversion)
- Faster inference, lower quality
- Use only if modernbert-embed-base has compatibility issues with mlx-embeddings

### Claude API (Hybrid ML)

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| anthropic | >=0.84.0 | Claude API SDK | For ambiguous/low-confidence email classification. Use Claude Haiku 4.5 ($1/$5 per 1M tokens) for cost efficiency. Batch API provides 50% discount for non-urgent processing of accumulated ambiguous cases. | HIGH |

**Cost Model:**
- Target: <5% of emails hit Claude API (ambiguous cases only)
- At 25K emails, ~1,250 API calls max
- Haiku 4.5 batch pricing: ~$0.50/1M input tokens, ~$2.50/1M output tokens
- Estimated total cost: <$1 for the entire cleanup run
- Use batch API (`MessageBatches`) to submit up to 10K queries at 50% discount

### CLI & User Interface

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| typer | >=0.15.0 | CLI framework | Type-hint-driven CLI. Less boilerplate than argparse (used in v1) or click. Auto-generates help text from function signatures and docstrings. Built on click so all click features are available if needed. | HIGH |
| rich | >=14.0.0 | Terminal formatting | Tables, progress bars, colored output, panels, markdown rendering. The cleanup report with confidence tiers, category breakdowns, and interactive approval flow needs more than print(). Typer integrates with Rich natively. | HIGH |

**Why not Textual (full TUI)?** Overkill. This tool has a linear workflow: scan -> classify -> report -> approve -> execute. Rich's `Prompt`, `Confirm`, tables, and progress bars handle that without an event-driven framework. Textual adds complexity (CSS-like styling, async event loops) that doesn't pay off for a sequential CLI tool.

**Why not argparse?** v1 used argparse with `--stats`, `--report`, `--execute` flags. Typer provides the same subcommand structure with less code, automatic validation, and Rich integration. Switching cost is near zero.

### Text Preprocessing

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| re (stdlib) | built-in | Regex preprocessing | Strip email signatures, quoted replies, excessive whitespace, URLs. Regex is the right tool for these deterministic patterns. | HIGH |
| html.parser (stdlib) | built-in | Lightweight HTML fallback | BS4's parser backend. No C dependencies needed. | HIGH |

**No NLP library needed.** This is NOT a bag-of-words or TF-IDF approach. Embeddings handle semantic understanding. Preprocessing just needs to: (1) extract text from HTML, (2) strip noise (signatures, reply chains, boilerplate), (3) truncate to model context length. All achievable with stdlib + beautifulsoup4.

### Data & Persistence

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| json (stdlib) | built-in | Classification results, config | v1 used JSON for reports. Human-readable, easy to edit for manual overrides. Store classification results, confidence scores, and user approvals. | HIGH |
| dataclasses (stdlib) | built-in | Data models | Clean typed data containers for MailMessage, ClassificationResult, ContactReputation, etc. No need for pydantic -- we're not doing API validation. | HIGH |

### Testing

| Technology | Version | Purpose | Why | Confidence |
|---|---|---|---|---|
| pytest | >=8.0 | Test runner | Standard. Use fixtures for mock DB and sample .emlx files. | HIGH |
| pytest-cov | >=5.0 | Coverage | Track test coverage. | HIGH |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|---|---|---|---|
| Embedding library | mlx-embeddings | mlx-embedding-models | mlx-embedding-models (Taylor AI) is text-only and more focused, but mlx-embeddings has ModernBERT support and more recent activity. Both are 0.0.x -- pick the one with the model architecture we want. |
| Embedding library | mlx-embeddings | sentence-transformers | sentence-transformers uses PyTorch which doesn't leverage Apple GPU via MLX. Would use CPU only. MLX is the whole point of this project. |
| CLI | typer | argparse (stdlib) | argparse works but requires more boilerplate. v1 used it; v2 should upgrade DX since we're rebuilding anyway. |
| CLI | typer | click | click is Typer's backend. Typer adds type-hint ergonomics on top. No reason to use click directly. |
| TUI | rich | textual | Textual is a full TUI framework (event loops, widgets, CSS). Our workflow is linear, not interactive-dashboard. Rich is sufficient. |
| HTML parsing | beautifulsoup4 | lxml | lxml is faster but requires C compilation. BS4 with html.parser is fast enough for email bodies and has zero binary deps. |
| .emlx parsing | emlx | manual parsing | Could parse .emlx manually (bytecount line + email.message_from_string + plist). emlx library does exactly this in 50 lines. Saves writing boilerplate. |
| .emlx parsing | emlx | emlx_parse | emlx_parse is less maintained, fewer downloads. The `emlx` package by mikez is the canonical option. |
| Vector DB | numpy arrays (in-memory) | faiss / chromadb | 25K emails x 256-dim embeddings = ~25MB. Fits trivially in memory. No need for a vector database. Cosine similarity via numpy dot product is fast enough for one-shot classification. |
| Data models | dataclasses | pydantic | No API validation, no serialization complexity. dataclasses are simpler and stdlib. |
| Claude SDK | anthropic | litellm | Direct SDK is cleaner for a single-provider integration. litellm adds abstraction we don't need. |

## Architecture-Relevant Stack Notes

### .emlx File Location Pattern
```
~/Library/Mail/V10/{account-uuid}/{mailbox}.mbox/{subfolder}/Messages/{message-id}.emlx
```
- Account UUID for iCloud: `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX` (from v1)
- The Envelope Index DB maps message IDs to mailbox ROWIDs; we need to resolve the filesystem path ourselves
- .emlx files may not exist for all messages (if Apple Mail hasn't cached them locally)

### Envelope Index Schema (from v1, verified)
```sql
-- Core join pattern
messages.message_id = message_global_data.message_id  -- NOT ROWID
-- Date is standard Unix timestamp (no Apple epoch offset)
-- Sender: messages.sender -> addresses.ROWID -> addresses.address
-- Mailbox: messages.mailbox -> mailboxes.ROWID -> mailboxes.url
```

### MLX Embedding Pipeline Shape
```python
from mlx_embeddings.utils import load
model, tokenizer = load("nomic-ai/modernbert-embed-base")

# Batch encode (GPU-accelerated on M1 Max)
texts = ["email body 1", "email body 2", ...]
embeddings = model.encode(texts)  # returns mlx.core.array

# Convert to numpy for similarity
import numpy as np
embeddings_np = np.array(embeddings)
```
**Note:** Exact API may differ -- verify against mlx-embeddings docs at implementation time. The library is 0.0.x and API may shift.

## Installation

```bash
# Initialize project with uv
uv init icloud-mail-cleanup-v2
cd icloud-mail-cleanup-v2

# Core dependencies
uv add mlx "mlx-embeddings>=0.0.5" numpy beautifulsoup4 emlx typer "rich>=14.0" anthropic

# Dev dependencies
uv add --dev pytest pytest-cov

# Verify MLX GPU access
uv run python -c "import mlx.core as mx; print(mx.default_device())"
# Expected: Device(gpu, 0)
```

### Python Version Consideration

Python 3.13.7 is installed on the machine. MLX core supports 3.13. However, mlx-embeddings requires `>=3.8` per its PyPI metadata -- should be fine. If any transitive dependency has issues with 3.13, create a 3.12 venv:

```bash
uv venv --python 3.12
```

## Version Pinning Strategy

**Pin loosely in pyproject.toml, pin exactly in uv.lock:**
- `mlx >= 0.22.0` -- fast-moving, want latest GPU optimizations
- `mlx-embeddings >= 0.0.5` -- early-stage, minor versions may break
- `anthropic >= 0.84.0` -- stable SDK, safe to float
- `rich >= 14.0` -- stable, backward-compatible
- `typer >= 0.15.0` -- stable API
- `emlx == 1.0.4` -- effectively abandonware (format is frozen), pin exact
- `beautifulsoup4 >= 4.12` -- stable

The `uv.lock` file will pin exact transitive versions. Commit it to git.

## Sources

- [MLX 0.31.0 documentation](https://ml-explore.github.io/mlx/build/html/index.html) -- framework docs, install requirements
- [MLX PyPI](https://pypi.org/project/mlx/) -- version history, Python compatibility
- [mlx-embeddings GitHub (Blaizzy)](https://github.com/Blaizzy/mlx-embeddings) -- model support, API
- [mlx-embeddings PyPI](https://pypi.org/project/mlx-embeddings/) -- version 0.0.5 (Oct 2025)
- [mlx-embedding-models GitHub (Taylor AI)](https://github.com/taylorai/mlx_embedding_models) -- alternative considered
- [emlx GitHub (mikez)](https://github.com/mikez/emlx) -- .emlx parser source
- [emlx PyPI](https://libraries.io/pypi/emlx) -- version 1.0.4
- [nomic-ai/modernbert-embed-base (HuggingFace)](https://huggingface.co/nomic-ai/modernbert-embed-base) -- embedding model
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) -- v0.84.0
- [Anthropic Message Batches API](https://www.anthropic.com/news/message-batches-api) -- 50% discount batch processing
- [Anthropic Pricing](https://platform.claude.com/docs/en/about-claude/pricing) -- Haiku 4.5 token costs
- [Typer docs](https://typer.tiangolo.com/) -- CLI framework
- [Rich 14.x docs](https://rich.readthedocs.io/en/stable/introduction.html) -- terminal formatting
- [Beautiful Soup 4.14.3 docs](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) -- HTML parsing
- [uv documentation](https://docs.astral.sh/uv/guides/projects/) -- project management
- v1 codebase at `~/claude_code_projects/icloud-mail-cleanup/` -- Envelope Index schema, query patterns
