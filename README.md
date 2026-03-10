# iCloud Mail Cleanup v2

Intelligent iCloud email classification and cleanup tool that replaces Apple Mail's unreliable categorization with multi-signal scoring, MLX content analysis, and interactive review.

## Why This Exists

After 15+ years of iCloud email, my inbox had tens of thousands of messages — newsletters I never unsubscribed from, automated notifications from services I no longer use, marketing blasts mixed in with emails from real people I actually care about.

Apple Mail's built-in categorization is unreliable. It misclassifies personal emails as junk and lets obvious spam through. Third-party cleanup tools either require forwarding your email to external servers (privacy nightmare) or use simplistic sender-based rules that can't distinguish a shipping notification from a marketing blast sent by the same domain.

I needed something that:
- Runs **entirely on-device** — no email data leaves my machine
- Goes beyond sender reputation — actually reads email content using **local ML on Apple Silicon**
- Understands that an email archive is a **data asset**, not just clutter — old friendships, career history, and memories must be protected
- Lets me **review before deleting** — aggressive classification with zero false positives on things that matter
- Operates **non-destructively** — moves to Trash (never permanent delete), with full undo capability

This tool is the result: a multi-phase pipeline that combines 14 behavioral/authentication signals, GPU-accelerated content embeddings, a feedback learning loop, and interactive web-based review to clean up years of accumulated email safely.

## What It Does

- Reads the local Envelope Index SQLite database and `.emlx` files (read-only — never modifies mail data directly)
- Multi-signal classification: contact reputation, behavioral patterns, email authentication (DKIM/SPF/DMARC), disposable domain detection, Apple Intelligence flags, content analysis via MLX embeddings
- 4-tier system: **Trash** / **Keep-Active** / **Keep-Historical** / **Review**
- Web-based review UI with cluster navigation, bulk actions, and keyboard shortcuts
- Feedback loop: review decisions train per-sender preferences for future runs
- Safe execution: batch AppleScript moves to Trash (never permanent delete), with action log and restore capability
- Optional Claude API fallback for remaining ambiguous emails (metadata-only payloads — never sends body text)

## Requirements

- macOS with Apple Mail (Envelope Index database required)
- Apple Silicon Mac (M1/M2/M3/M4) for MLX GPU embeddings
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
git clone https://github.com/JaviOFC/icloud-mail-cleanup-v2.git
cd icloud-mail-cleanup-v2
uv sync
```

## Usage

The tool provides 6 subcommands that form a pipeline. Run them in order for a typical cleanup session.

### Global Options

```
--db PATH           Override Envelope Index database path
--checkpoint PATH   Override checkpoint file path (default: ~/.icloud-cleanup/checkpoint.jsonl)
-v, --verbose       Enable debug logging
```

### Typical Workflow

```
classify --full --analyze  →  review --web  →  execute --execute
```

### classify — Multi-Signal Classification

```bash
uv run python -m icloud_cleanup classify                          # incremental
uv run python -m icloud_cleanup classify --full                   # full reclassification
uv run python -m icloud_cleanup classify --full --analyze         # classify + embeddings + clustering
uv run python -m icloud_cleanup classify --debug-scores user@example.com
```

Runs the 14-signal weighted scoring pipeline on all messages. Extracts DKIM/SPF/DMARC authentication headers from `.emlx` files. Loads feedback from previous review sessions. Supports incremental mode by default (only classifies new messages).

With `--analyze`, also runs content analysis: parses `.emlx` email bodies, generates MLX embeddings on Apple Silicon GPU, clusters via HDBSCAN, and fuses content scores with metadata scores.

| Flag | Description |
|-|-|
| `--full` | Force full reclassification, ignoring existing checkpoint |
| `--analyze` | Run content analysis (embeddings + clustering + score fusion) after classification |
| `--mail-dir PATH` | Override the Mail V10 directory (default: `~/Library/Mail/V10`) |
| `--debug-scores SENDER` | Dump per-signal breakdown for a specific sender address |

### analyze — Content Analysis Only

```bash
uv run python -m icloud_cleanup analyze
uv run python -m icloud_cleanup analyze --mail-dir /path/to/Mail/V10
```

Runs content analysis separately (if you've already classified). Parses `.emlx` bodies, generates embeddings, clusters, and fuses scores.

### report — Classification Report

```bash
uv run python -m icloud_cleanup report
uv run python -m icloud_cleanup report --format json --output ./reports
uv run python -m icloud_cleanup report --format markdown
```

Displays or exports classification results. Terminal output shows tier summaries and top senders per tier.

| Flag | Description |
|-|-|
| `--format terminal\|json\|markdown\|all` | Output format (default: `terminal`) |
| `--output DIR` | Directory for exported report files |

### review — Interactive Web Review

```bash
uv run python -m icloud_cleanup review --web       # launch web UI at localhost:8899
uv run python -m icloud_cleanup review             # terminal review (legacy)
uv run python -m icloud_cleanup review --reset     # discard session and start fresh
```

Launches a web-based review UI for deciding on classified emails. Features:
- Cluster sidebar with progress indicators
- Bulk actions: select and trash/keep multiple emails at once
- Domain and tier filtering, confidence range slider
- Keyboard shortcuts (j/k navigate, d/k/u decide, x toggle select)
- Compact and sender-grouped view modes
- Sessions auto-save after each decision for crash-safe resumability

| Flag | Description |
|-|-|
| `--web` | Launch web review UI (recommended) |
| `--resume` | Continue an existing review session |
| `--reset` | Discard existing session and start fresh |
| `--session PATH` | Custom session file path |

### execute — Execute Approved Deletions

```bash
uv run python -m icloud_cleanup execute              # dry-run (default)
uv run python -m icloud_cleanup execute --execute    # actually move to Trash
uv run python -m icloud_cleanup execute --restore    # undo previous deletions
```

Carries out deletions approved during review. Dry-run by default — pass `--execute` to actually move messages to Trash via batch AppleScript. Records per-sender feedback for the learning loop.

| Flag | Description |
|-|-|
| `--execute` | Actually perform deletions (default: dry-run) |
| `--restore` | Restore previously deleted messages from action log |
| `--batch-size N` | Messages per AppleScript batch (default: 100) |
| `--batch-pause N` | Seconds between batches (default: 2.0) |
| `--action-log PATH` | Custom action log path (default: `~/.icloud-cleanup/action_log.db`) |

## How Classification Works

### Phase 1: Metadata Scoring (14 signals)

Ten always-on signals plus four optional signals produce a confidence score (0–1) per message:

**Always-on signals:**
1. **Contact reputation** (0.20) — bidirectional communication, system contacts match
2. **Frequency** (0.10) — volume normalized against engagement
3. **Recency** (0.10) — when was the last interaction?
4. **Reply rate** (0.12) — how often have you replied to this sender?
5. **Apple category** (0.10) — Apple Mail's internal categorization
6. **Apple high-impact** (0.05) — Apple Intelligence importance flag
7. **Automation detection** (0.08) — automated conversation indicators
8. **Flagged history** (0.04) — has the user flagged emails from this sender?
9. **Mailing list** (0.05) — List-ID header present
10. **No-reply sender** (0.03) — noreply/mailer-daemon patterns

**Optional signals (fire only when informative):**
11. **Junk level** (0.07) — iCloud spam classification (from `server_messages` table)
12. **Urgent** (0.05) — Apple Intelligence urgency flag
13. **Disposable domain** (0.05) — sender domain on disposable email blocklist (5,197 domains)
14. **Email authentication** (0.06) — DKIM/SPF/DMARC results extracted from `.emlx` headers

**Feedback signal** (0.10) — Laplace-smoothed per-sender preference from previous review sessions. Omitted on first run.

### Phase 2: Content Analysis

- MLX embeddings (Apple Silicon GPU) generate vector representations of email bodies
- HDBSCAN clustering with leaf selection groups similar emails; sub-clustering for oversized clusters
- TF-IDF labeling names each cluster
- Content scores fuse with metadata scores for final tier assignment

### Protection Rules

Emails from contacts you've replied to, sent to, or that match system contacts are **protected from Trash** regardless of other signals. Protection can only be overridden at extremely low engagement (read rate < 5%).

## Architecture

| Module | Purpose |
|-|-|
| `scanner` | Reads Envelope Index SQLite DB, extracts messages and sender stats |
| `contacts` | Builds contact reputation profiles from behavioral signals + system contacts |
| `classifier` | 14-signal weighted scoring, tier assignment, confidence computation |
| `emlx_parser` | Parses `.emlx` files for body text extraction and authentication headers |
| `embedder` | MLX GPU embedding generation for email content |
| `clusterer` | HDBSCAN clustering + TF-IDF cluster labeling + content score derivation |
| `feedback` | SQLite-backed per-sender feedback store for learning loop |
| `auto_triage` | Automatic resolution of high-confidence Review-tier items |
| `propagation` | Domain-level and subdomain decision propagation across clusters |
| `report` | Terminal, JSON, and Markdown report generation |
| `review` | Review session management with crash-safe persistence |
| `web` | Flask web server + single-file HTML review UI |
| `executor` | Batch AppleScript trash execution with action log and restore |
| `api_fallback` | Claude API integration for ambiguous emails (metadata-only payloads) |
| `checkpoint` | JSONL checkpoint save/load for incremental classification |
| `models` | Domain dataclasses: Message, ContactProfile, Classification, Tier |
| `display` | Rich terminal output: progress bars, tier summaries, tables |

## Testing

```bash
uv run pytest
```

464 tests covering all modules.

## Data Safety

- **Read-only access** — all queries against the Envelope Index are SELECT-only
- **No permanent deletes** — deletions use AppleScript `set mailbox of` to move messages to Trash
- **Action log** — every deletion is recorded in a SQLite action log with full restore capability
- **Dry-run by default** — the `execute` command requires an explicit `--execute` flag
- **Feedback loop** — review decisions improve future classification, stored locally
- **Privacy** — all classification happens on-device; Claude API (if used) receives metadata-only payloads, never email body text
