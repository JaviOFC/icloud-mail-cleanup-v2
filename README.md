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

This tool is the result: a multi-phase pipeline that combines 8 behavioral signals, GPU-accelerated content embeddings, and interactive review to clean up years of accumulated email safely.

## What It Does

- Reads the local Envelope Index SQLite database and `.emlx` files (read-only -- never modifies mail data directly)
- Multi-signal classification: contact reputation, behavioral patterns (read/reply/flag), content analysis via MLX embeddings on Apple Silicon GPU
- 4-tier system: **Trash** / **Keep-Active** / **Keep-Historical** / **Review**
- Interactive terminal review with auto-triage for high-confidence items
- Safe execution: moves to Trash via AppleScript (never permanent delete), with action log and restore capability
- Optional Claude API fallback for remaining ambiguous emails (metadata-only payloads -- never sends body text)

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
--db PATH        Override Envelope Index database path
--checkpoint PATH   Override checkpoint file path (default: ~/.icloud-cleanup/checkpoint.jsonl)
-v, --verbose    Enable debug logging
```

### Typical Workflow

```
scan -> classify -> analyze -> report -> review -> execute
```

### scan -- Sender Volume Statistics

```bash
uv run icloud_cleanup scan
```

Shows email counts per sender, giving a quick overview of your inbox composition.

### classify -- Metadata Classification (Phase 1)

```bash
uv run icloud_cleanup classify
uv run icloud_cleanup classify --full
uv run icloud_cleanup classify --debug-scores user@example.com
```

Runs the 8-signal weighted scoring pipeline on all messages. Supports incremental mode by default (only classifies new messages). Results are saved to a checkpoint file.

| Flag | Description |
|-|-|
| `--full` | Force full reclassification, ignoring existing checkpoint |
| `--debug-scores SENDER` | Dump per-signal breakdown for a specific sender address |

### analyze -- Content Analysis with MLX Embeddings (Phase 2)

```bash
uv run icloud_cleanup analyze
uv run icloud_cleanup analyze --mail-dir /path/to/Mail/V10
```

Parses `.emlx` email bodies, generates embeddings on the Apple Silicon GPU, clusters similar emails via HDBSCAN, and fuses content scores with Phase 1 metadata scores for improved classification.

| Flag | Description |
|-|-|
| `--mail-dir PATH` | Override the Mail V10 directory (default: `~/Library/Mail/V10`) |

### report -- Classification Report

```bash
uv run icloud_cleanup report
uv run icloud_cleanup report --format json --output ./reports
uv run icloud_cleanup report --format markdown
uv run icloud_cleanup report --format all --output ./reports
```

Displays or exports the classification results. Terminal output shows tier summaries and top senders per tier.

| Flag | Description |
|-|-|
| `--format terminal\|json\|markdown\|all` | Output format (default: `terminal`) |
| `--json` | Shorthand for `--format json` |
| `--markdown` | Shorthand for `--format markdown` |
| `--output DIR` | Directory for exported report files |

### review -- Interactive Review Session

```bash
uv run icloud_cleanup review
uv run icloud_cleanup review --resume
uv run icloud_cleanup review --reset
```

Launches an interactive terminal session to review classified emails. Auto-triage handles high-confidence items automatically, then presents remaining clusters for manual approve/skip/reclassify decisions. Sessions are saved after each decision for crash-safe resumability.

| Flag | Description |
|-|-|
| `--resume` | Continue an existing review session |
| `--reset` | Discard existing session and start fresh |
| `--session PATH` | Custom session file path |

### execute -- Execute Approved Deletions

```bash
uv run icloud_cleanup execute              # dry-run (default)
uv run icloud_cleanup execute --execute    # actually move to Trash
uv run icloud_cleanup execute --restore    # undo previous deletions
```

Carries out deletions approved during review. Dry-run by default -- pass `--execute` to actually move messages to Trash via AppleScript. Supports batch rate limiting and full restore from the action log.

| Flag | Description |
|-|-|
| `--execute` | Actually perform deletions (default: dry-run) |
| `--restore` | Restore previously deleted messages from action log |
| `--batch-size N` | Messages per AppleScript batch (default: 100) |
| `--batch-pause N` | Seconds between batches (default: 2.0) |
| `--action-log PATH` | Custom action log path (default: `~/.icloud-cleanup/action_log.db`) |

## How Classification Works

### Phase 1: Metadata Scoring

Eight weighted signals produce a confidence score (0-1) per message:

1. **Contact reputation** -- have you sent to or received replies from this sender?
2. **Read rate** -- what fraction of this sender's emails have you read?
3. **Reply rate** -- how often have you replied to this sender?
4. **Recency** -- when was the last interaction?
5. **Frequency** -- volume normalized against engagement
6. **List-ID presence** -- is this a mailing list?
7. **Document attachments** -- emails with document attachments score higher
8. **Mailing list flags** -- automated conversation and unsubscribe indicators

### Phase 2: Content Analysis

- MLX embeddings (Apple Silicon GPU) generate vector representations of email bodies
- HDBSCAN clustering groups similar emails
- TF-IDF labeling names each cluster
- Content scores fuse with metadata scores for final tier assignment

### Protection Rules

Emails from contacts you've replied to, sent to, or that match system contacts are **protected from Trash** regardless of other signals. Protection can only be overridden at extremely low engagement (read rate < 5%).

## Architecture

| Module | Purpose |
|-|-|
| `scanner` | Reads Envelope Index SQLite DB, extracts messages and sender stats |
| `contacts` | Builds contact reputation profiles from behavioral signals + system contacts |
| `classifier` | 8-signal weighted scoring, tier assignment, confidence computation |
| `emlx_parser` | Parses `.emlx` files to extract email body text |
| `embedder` | MLX GPU embedding generation for email content |
| `clusterer` | HDBSCAN clustering + TF-IDF cluster labeling + content score derivation |
| `auto_triage` | Automatic resolution of high-confidence Review-tier items |
| `propagation` | Domain-level and subdomain decision propagation across clusters |
| `report` | Terminal, JSON, and Markdown report generation |
| `review` | Interactive terminal review session with crash-safe persistence |
| `executor` | AppleScript-based trash execution with action log and restore |
| `api_fallback` | Claude API integration for ambiguous emails (metadata-only payloads) |
| `checkpoint` | JSONL checkpoint save/load for incremental classification |
| `models` | Domain dataclasses: Message, ContactProfile, Classification, Tier |
| `display` | Rich terminal output: progress bars, tier summaries, tables |

## Testing

```bash
uv run pytest
```

348 tests covering all modules.

## Data Safety

- **Read-only access** -- all queries against the Envelope Index are SELECT-only
- **No permanent deletes** -- deletions use AppleScript `set mailbox of` to move messages to Trash
- **Action log** -- every deletion is recorded in a SQLite action log with full restore capability
- **Dry-run by default** -- the `execute` command requires an explicit `--execute` flag
- **Privacy** -- all classification happens on-device; Claude API (if used) receives metadata-only payloads, never email body text
