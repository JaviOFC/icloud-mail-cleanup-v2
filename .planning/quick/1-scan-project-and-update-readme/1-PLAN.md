---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified: [README.md]
autonomous: true
requirements: [QUICK-01]
must_haves:
  truths:
    - "README.md accurately describes the project purpose, features, and usage"
    - "All CLI subcommands are documented with examples"
    - "Installation and prerequisites are clear"
  artifacts:
    - path: "README.md"
      provides: "Complete project documentation"
      min_lines: 80
  key_links: []
---

<objective>
Write a comprehensive README.md for the icloud-mail-cleanup-v2 project based on the actual codebase.

Purpose: The project is feature-complete (3 phases done, 348 tests) but has an empty README. Need accurate documentation reflecting what's actually built.
Output: README.md at project root
</objective>

<execution_context>
@.claude/get-shit-done/workflows/execute-plan.md
@.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@src/icloud_cleanup/cli.py
@src/icloud_cleanup/models.py
@pyproject.toml
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write README.md</name>
  <files>README.md</files>
  <action>
Create README.md with the following sections based on codebase analysis:

**Header:** "iCloud Mail Cleanup v2" with one-line description: intelligent iCloud email classification and cleanup tool that replaces Apple Mail's unreliable categorization.

**What it does (brief):**
- Reads the local Envelope Index SQLite DB and .emlx files (read-only, never modifies mail data directly)
- Multi-signal classification: contact reputation, behavioral patterns (read/reply/flag), content analysis via MLX embeddings on Apple Silicon GPU
- 4-tier system: Trash / Keep-Active / Keep-Historical / Review
- Interactive terminal review with auto-triage for high-confidence items
- Safe execution: moves to Trash via AppleScript (never permanent delete), with action log and restore capability
- Optional Claude API fallback for remaining ambiguous emails (metadata-only payloads, never sends body text)

**Requirements:**
- macOS (Apple Mail + Envelope Index required)
- Apple Silicon Mac (M1/M2/M3) for MLX GPU embeddings
- Python 3.11+
- uv package manager

**Installation:**
```
git clone <repo>
cd icloud-mail-cleanup-v2
uv sync
```

**Usage -- document all 6 subcommands from cli.py:**

1. `uv run icloud_cleanup scan` -- Show sender volume statistics
2. `uv run icloud_cleanup classify` -- Run metadata classification pipeline (Phase 1)
   - `--full` to force full reclassification
   - `--debug-scores SENDER` for per-signal breakdown
3. `uv run icloud_cleanup analyze` -- Run content analysis with MLX embeddings (Phase 2)
   - `--mail-dir PATH` to override Mail V10 directory
4. `uv run icloud_cleanup report` -- Display/export classification report
   - `--format terminal|json|markdown|all`
   - `--output DIR` for export directory
5. `uv run icloud_cleanup review` -- Interactive review session
   - `--resume` to continue existing session
   - `--reset` to start fresh
6. `uv run icloud_cleanup execute` -- Execute approved deletions
   - Dry-run by default, `--execute` to actually perform
   - `--restore` to undo previous deletions
   - `--batch-size N` and `--batch-pause N` for rate limiting

**Global options:** `--db PATH` (override DB path), `--checkpoint PATH`, `-v` (verbose)

**Typical workflow:** scan -> classify -> analyze -> report -> review -> execute

**How classification works (brief):**
- Phase 1 (metadata): 8-signal weighted scoring -- contact reputation, read rate, reply rate, recency, frequency, list-id presence, document attachments, mailing list flags
- Phase 2 (content): MLX embeddings + HDBSCAN clustering + TF-IDF labeling, fused with metadata scores
- Protection: emails from contacts you've replied to, sent to, or that match system contacts are protected from Trash regardless of other signals

**Architecture (brief):** List the key modules (scanner, contacts, classifier, emlx_parser, embedder, clusterer, auto_triage, report, review, executor, api_fallback) with one-line descriptions.

**Testing:**
```
uv run pytest
```
348 tests covering all modules.

**Data safety:**
- All reads are read-only against the Envelope Index
- Deletions use AppleScript `set mailbox of` (moves to Trash, never permanent delete)
- Complete action log with restore capability
- Dry-run by default on execute
- Claude API (if used) receives metadata-only payloads, never email body text

Keep it clean -- no badges, no emojis, no unnecessary boilerplate. Markdown headers, code blocks, concise prose. Match the style of Javi's global CLAUDE.md preferences: direct, no fluff.
  </action>
  <verify>
    <automated>test -s README.md && wc -l README.md | awk '{if ($1 >= 80) print "PASS: " $1 " lines"; else print "FAIL: only " $1 " lines"}'</automated>
  </verify>
  <done>README.md exists with 80+ lines covering all sections: description, requirements, installation, all 6 CLI subcommands with flags, workflow, classification overview, architecture, testing, and data safety</done>
</task>

</tasks>

<verification>
- README.md is accurate to actual CLI (all 6 subcommands match cli.py)
- No claims about features that don't exist
- Installation instructions use uv (per project convention)
- No emojis (per user preference)
</verification>

<success_criteria>
README.md is a complete, accurate reference for the project that someone could use to install, understand, and operate the tool without reading source code.
</success_criteria>

<output>
After completion, create `.planning/quick/1-scan-project-and-update-readme/1-SUMMARY.md`
</output>
