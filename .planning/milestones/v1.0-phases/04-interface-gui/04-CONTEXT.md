# Phase 4: Interface & GUI (TUI) - Context

**Gathered:** 2026-03-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Build an interactive Textual-based terminal application (TUI) that complements the existing CLI subcommands. The TUI provides a navigable, panel-based interface for reviewing classification results, executing deletions, visualizing data, and optionally triggering the scan/classify/analyze pipeline — replacing the sequential questionary-based review with a rich interactive experience. Web app is deferred to a future Phase 5.

</domain>

<decisions>
## Implementation Decisions

### TUI scope
- **Complement, not replace** — CLI subcommands (scan, classify, analyze, report, review, execute) stay for batch/scripted use. TUI is a new `tui` subcommand for interactive workflows
- **Auto-detect with overrides** — Auto-find checkpoint at `~/.icloud-cleanup/checkpoint.jsonl` and review session. Allow `--checkpoint` and `--session` CLI overrides (same pattern as existing subcommands)
- **Pipeline triggerable from TUI** — Include a Pipeline screen that can kick off scan→classify→analyze with live progress, not just view existing data
- **Claude API fallback in TUI** — After review, show remaining ambiguous count + estimated cost with a 'Run API Analysis' action. Full API flow within the TUI

### Layout & navigation
- **Dashboard + screens** — Launch into a dashboard showing tier summary, storage stats, pipeline status. Navigate to separate screens: Dashboard, Review, Execute, Pipeline
- **Header tabs + hotkeys** — Clickable tab bar at top AND keyboard shortcuts (D/R/E/P). Supports both mouse and keyboard users
- **Review: list + detail split** — Left panel: scrollable cluster list (name, count, tier). Right panel: selected cluster detail (emails, senders, confidence, action buttons)
- **Inspect: inline expand** — When inspecting a cluster, the detail panel expands to show individual email list within the same split view. No modal or third pane

### Review interaction
- **Auto-triage: manual trigger** — Review screen shows all clusters raw. User clicks 'Run Auto-Triage' button to narrow the list. Not automatic on launch
- **Bulk actions: multi-select** — Space to toggle selection on clusters, then apply action (Approve All, Skip All) to selected batch. File-manager pattern
- **Propagation: both inline + tab** — After approving a cluster, immediately show propagation suggestion as a toast/popup. Also a dedicated Propagation tab for reviewing all suggestions afterward
- **Execute: live progress** — Real-time display: progress bar, current batch, success/error count updating live as deletions execute

### Data visualization
- **Rich panels + sparklines** — Tier summary table with inline sparklines for confidence distribution per tier. Color-coded bars using Textual's built-in widgets
- **Storage impact: prominent** — Big number on dashboard: 'Potential savings: X GB (N emails)'. Updates as clusters are approved/skipped during review
- **Confidence: sparkline + per-email bars** — Sparkline summary in cluster header for distribution shape. When inspecting individual emails, each row shows confidence as a colored bar (red=low, green=high)
- **Pipeline: progress + log tail** — Progress bar at top, scrollable log output below showing step details (parsing, embedding, clustering). Build-output style

### UI polish
- **Theme toggle** — Dark and light themes, user-selectable. Textual has native theme support
- **Tier colors: consistent** — Same TIER_COLORS from models.py (red=Trash, green=Active, blue=Historical, yellow=Review). No redesign
- **Help: footer + overlay** — Common shortcuts always visible in footer bar. Press ? to open full keyboard shortcut reference overlay
- **Fixed layout proportions** — No persisted window/pane sizes. Use sensible defaults every launch

### Claude's Discretion
- Textual widget selection and custom widget design
- Exact split pane proportions (cluster list vs detail panel)
- Toast/notification styling for propagation prompts
- CSS theming approach for dark/light modes
- Pipeline screen async worker pattern (Textual workers vs threading)
- Footer bar layout and which shortcuts to show per screen
- Exact key bindings beyond the discussed D/R/E/P navigation

</decisions>

<specifics>
## Specific Ideas

- Dashboard mockup: tier summary panel with counts and percentages, prominent storage savings number, pipeline status indicator, navigation to Review/Execute/Pipeline screens
- Review screen: two-column split — cluster list on left, detail on right. Arrow keys navigate clusters, Space toggles selection, A/S/I for Approve/Skip/Inspect
- Textual is by the same author as Rich (Will McGuigan) — natural upgrade path from existing Rich-based display code
- The `_confidence_sparkline()` function in report.py already generates unicode sparklines — reuse in TUI widgets

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `display.py`: `display_tier_summary()`, `display_top_senders()`, `display_cluster_summary()` — logic reusable, presentation needs Textual widget wrappers
- `report.py`: `_confidence_sparkline()`, `_cluster_key()`, report data builders — reusable for TUI dashboard and detail views
- `review.py`: `ReviewSession`, `save_session()`, `load_session()`, `run_review()` — session state model reusable, interactive loop replaced by TUI event handlers
- `auto_triage.py`: `auto_triage()` — callable from TUI on button press
- `propagation.py`: propagation engine — callable from TUI after approve actions
- `executor.py`: `ActionLog`, `execute_deletions()`, `restore_from_log()` — callable from TUI execute screen
- `api_fallback.py`: `estimate_api_cost()`, `classify_ambiguous_batch()` — callable from TUI API fallback flow
- `models.py`: `TIER_COLORS` dict — reuse for consistent color coding across CLI and TUI
- `cli.py`: `cmd_classify()`, `cmd_analyze()` — pipeline logic to wrap in TUI async workers

### Established Patterns
- Subcommand-based CLI (argparse) — TUI becomes another subcommand
- Dataclass-based domain models with type hints
- Checkpoint JSONL as data interchange
- Atomic file writes via tmp + `os.replace`
- `rich` library already in use — Textual is the natural TUI extension

### Integration Points
- New `cmd_tui()` function in `cli.py` with `tui` subcommand
- Reads same checkpoint JSONL and review session JSON as existing commands
- Writes same review session format — session started in TUI can be resumed in CLI and vice versa
- Execute screen uses same `executor.py` functions — same action log SQLite
- Pipeline screen calls same classify/analyze logic, just with Textual progress widgets instead of Rich progress bars

</code_context>

<deferred>
## Deferred Ideas

- Web app (FastAPI + browser UI) — Phase 5
- macOS native app (SwiftUI/PyQt) — not planned
- Persisted layout preferences between sessions — skip for Phase 4, add if users request

</deferred>

---

*Phase: 04-interface-gui*
*Context gathered: 2026-03-05*
