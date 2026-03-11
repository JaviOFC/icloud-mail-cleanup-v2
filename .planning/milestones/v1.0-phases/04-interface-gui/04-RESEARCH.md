# Phase 4: Interface & GUI (TUI) - Research

**Researched:** 2026-03-05
**Domain:** Textual TUI framework, terminal UI architecture, async worker patterns
**Confidence:** HIGH

## Summary

Phase 4 builds a Textual-based TUI application as a new `tui` subcommand that complements the existing CLI. The TUI provides a multi-screen interactive experience: Dashboard (tier summaries, storage stats), Review (cluster list + detail split), Execute (live progress), and Pipeline (scan/classify/analyze with progress + log). All existing business logic modules (auto_triage, propagation, executor, api_fallback, report, review session) are reused directly -- the TUI replaces only the presentation layer (Rich tables + questionary prompts) with Textual widgets and event-driven interactions.

Textual 8.0.2 (latest, March 2026) is a mature framework by Will McGuigan (author of Rich, already in the project). It provides CSS-based styling, built-in dark/light themes, a comprehensive widget library (DataTable, Sparkline, RichLog, SelectionList, TabbedContent, ProgressBar), async workers for background tasks, and a Pilot-based testing API. The framework is well-documented with stable APIs.

**Primary recommendation:** Use Textual modes (not TabbedContent) for top-level navigation between Dashboard/Review/Execute/Pipeline screens, with per-screen TCSS files for styling. Use `@work` decorator for pipeline and execution background tasks. Reuse all existing domain modules unchanged.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- TUI scope: Complement, not replace -- CLI subcommands stay for batch/scripted use. TUI is a new `tui` subcommand
- Auto-detect with overrides -- Auto-find checkpoint at `~/.icloud-cleanup/checkpoint.jsonl` and review session. Allow `--checkpoint` and `--session` CLI overrides
- Pipeline triggerable from TUI -- Pipeline screen can kick off scan->classify->analyze with live progress
- Claude API fallback in TUI -- After review, show remaining ambiguous count + estimated cost with a 'Run API Analysis' action
- Dashboard + screens layout -- Launch into dashboard showing tier summary, storage stats, pipeline status. Navigate to Dashboard, Review, Execute, Pipeline screens
- Header tabs + hotkeys -- Clickable tab bar at top AND keyboard shortcuts (D/R/E/P). Mouse and keyboard support
- Review: list + detail split -- Left panel: scrollable cluster list. Right panel: selected cluster detail
- Inspect: inline expand -- Detail panel expands to show individual email list within same split view. No modal or third pane
- Auto-triage: manual trigger -- Review screen shows all clusters raw. User clicks 'Run Auto-Triage' button
- Bulk actions: multi-select -- Space to toggle selection on clusters, then apply action to selected batch
- Propagation: both inline + tab -- After approving, show propagation suggestion as toast/popup. Also dedicated Propagation tab
- Execute: live progress -- Real-time progress bar, current batch, success/error count updating live
- Rich panels + sparklines -- Tier summary table with inline sparklines for confidence distribution
- Storage impact: prominent -- Big number on dashboard: 'Potential savings: X GB (N emails)'
- Confidence: sparkline + per-email bars -- Sparkline summary in cluster header, per-email colored confidence bars
- Pipeline: progress + log tail -- Progress bar at top, scrollable log output below
- Theme toggle -- Dark and light themes, user-selectable
- Tier colors: consistent -- Same TIER_COLORS from models.py
- Help: footer + overlay -- Common shortcuts in footer bar. Press ? for full keyboard reference overlay
- Fixed layout proportions -- No persisted window/pane sizes

### Claude's Discretion
- Textual widget selection and custom widget design
- Exact split pane proportions (cluster list vs detail panel)
- Toast/notification styling for propagation prompts
- CSS theming approach for dark/light modes
- Pipeline screen async worker pattern (Textual workers vs threading)
- Footer bar layout and which shortcuts to show per screen
- Exact key bindings beyond D/R/E/P navigation

### Deferred Ideas (OUT OF SCOPE)
- Web app (FastAPI + browser UI) -- Phase 5
- macOS native app (SwiftUI/PyQt) -- not planned
- Persisted layout preferences between sessions
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | 8.0.2 | TUI framework | By Rich author, natural upgrade from existing Rich usage. Async, CSS styling, comprehensive widgets |
| rich | 14.3.3+ | Already in project | Textual's rendering engine. Rich renderables work in Textual widgets (RichLog, DataTable cells) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | latest | Async test support | Testing Textual apps requires async context |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Textual modes | TabbedContent at top | Modes give independent screen stacks, better for complex per-screen navigation |
| DataTable for clusters | ListView | DataTable provides sort, cursor_type="row", cell styling. ListView is simpler but less feature-rich |
| @work decorator | raw asyncio.create_task | @work integrates with Textual lifecycle (auto-cancel on screen pop), exclusive mode prevents races |

**Installation:**
```bash
uv add textual
uv add --dev pytest-asyncio
```

## Architecture Patterns

### Recommended Project Structure
```
src/icloud_cleanup/
    tui/
        __init__.py            # CleanupApp class, mode definitions
        app.tcss               # Global app CSS (header, footer, common)
        screens/
            __init__.py
            dashboard.py       # DashboardScreen
            dashboard.tcss
            review.py          # ReviewScreen (cluster list + detail split)
            review.tcss
            execute.py         # ExecuteScreen (progress, results)
            execute.tcss
            pipeline.py        # PipelineScreen (scan/classify/analyze)
            pipeline.tcss
            help_overlay.py    # HelpScreen (ModalScreen for ? key)
        widgets/
            __init__.py
            tier_summary.py    # TierSummaryWidget (table + sparklines)
            storage_banner.py  # StorageBannerWidget (big savings number)
            cluster_list.py    # ClusterListWidget (DataTable, multi-select)
            cluster_detail.py  # ClusterDetailWidget (info panel + email list)
            confidence_bar.py  # ConfidenceBarWidget (colored bar per email)
            pipeline_log.py    # PipelineLogWidget (RichLog wrapper)
    cli.py                     # Add cmd_tui() and 'tui' subcommand
```

### Pattern 1: App with Modes for Top-Level Navigation
**What:** Use Textual modes (named screen stacks) for Dashboard/Review/Execute/Pipeline
**When to use:** When screens are independent and need their own navigation context
**Example:**
```python
# Source: Textual official docs - Screens guide
from textual.app import App
from textual.binding import Binding

class CleanupApp(App):
    CSS_PATH = "tui/app.tcss"

    MODES = {
        "dashboard": "DashboardScreen",
        "review": "ReviewScreen",
        "execute": "ExecuteScreen",
        "pipeline": "PipelineScreen",
    }
    DEFAULT_MODE = "dashboard"

    BINDINGS = [
        Binding("d", "switch_mode('dashboard')", "Dashboard", priority=True),
        Binding("r", "switch_mode('review')", "Review", priority=True),
        Binding("e", "switch_mode('execute')", "Execute", priority=True),
        Binding("p", "switch_mode('pipeline')", "Pipeline", priority=True),
        Binding("question_mark", "push_screen('help')", "Help"),
        Binding("t", "toggle_dark", "Theme"),
        Binding("q", "quit", "Quit"),
    ]
```

### Pattern 2: Split Pane with Horizontal Container
**What:** Two-column layout for Review screen (cluster list left, detail right)
**When to use:** Master-detail views
**Example:**
```python
# Source: Textual layout guide
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

class ReviewScreen(Screen):
    CSS_PATH = "review.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="review-split"):
            yield ClusterListWidget(id="cluster-list")
            yield ClusterDetailWidget(id="cluster-detail")
        yield Footer()
```
```css
/* review.tcss */
#review-split {
    height: 1fr;
}
#cluster-list {
    width: 2fr;
    min-width: 40;
}
#cluster-detail {
    width: 3fr;
    min-width: 50;
}
```

### Pattern 3: Background Workers for Pipeline
**What:** Use `@work(exclusive=True)` for long-running pipeline operations
**When to use:** Pipeline scan/classify/analyze, execute deletions
**Example:**
```python
# Source: Textual Workers guide
from textual import work
from textual.widgets import ProgressBar, RichLog

class PipelineScreen(Screen):
    @work(exclusive=True, thread=True)
    def run_pipeline(self, checkpoint_path: Path, db_path: Path | None) -> None:
        """Run scan->classify->analyze in background thread."""
        worker = get_current_worker()
        log_widget = self.query_one("#pipeline-log", RichLog)
        progress = self.query_one("#pipeline-progress", ProgressBar)

        # Step 1: Scan
        self.call_from_thread(log_widget.write, "[bold]Step 1: Scanning...[/bold]")
        conn = open_db(db_path)
        messages = scan_messages(conn)
        if worker.is_cancelled:
            return
        self.call_from_thread(progress.update, advance=33)

        # ... classify, analyze steps ...
```

### Pattern 4: DataTable with Row Selection for Clusters
**What:** Use DataTable with cursor_type="row" for cluster navigation
**When to use:** Cluster list where selecting a row updates the detail pane
**Example:**
```python
from textual.widgets import DataTable
from rich.text import Text

class ClusterListWidget(DataTable):
    def __init__(self, **kwargs):
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)

    def on_mount(self) -> None:
        self.add_columns("Cluster", "Count", "Tier", "Confidence", "Dist")

    def load_clusters(self, clusters: list[dict]) -> None:
        self.clear()
        for cluster in clusters:
            tier_color = TIER_COLORS[cluster["tier"]]
            self.add_row(
                cluster["label"],
                str(cluster["count"]),
                Text(cluster["tier"].value, style=tier_color),
                f"{cluster['avg_conf']:.2f}",
                cluster["sparkline"],
                key=cluster["label"],
            )
```

### Pattern 5: Notifications for Propagation Suggestions
**What:** Use `self.notify()` for propagation toasts after approve actions
**When to use:** Inline feedback after cluster decisions
**Example:**
```python
# Source: Textual notify API
def handle_approve(self, cluster_key: str) -> None:
    # ... save decision ...
    suggestions = find_propagation_targets(...)
    if suggestions:
        total = sum(len(s.target_message_ids) for s in suggestions)
        self.notify(
            f"{total} similar emails found. Check Propagation tab.",
            title="Propagation Suggestion",
            severity="information",
            timeout=5,
        )
```

### Pattern 6: Testing with Pilot
**What:** Use `app.run_test()` with Pilot for headless testing
**When to use:** All TUI tests
**Example:**
```python
import pytest
from icloud_cleanup.tui import CleanupApp

@pytest.mark.asyncio
async def test_dashboard_shows_tier_summary():
    app = CleanupApp(checkpoint_path=test_checkpoint)
    async with app.run_test(size=(120, 40)) as pilot:
        # Dashboard is default mode
        assert app.screen.__class__.__name__ == "DashboardScreen"
        # Check tier summary widget exists
        tier_widget = app.query_one("#tier-summary")
        assert tier_widget is not None
```

### Anti-Patterns to Avoid
- **Blocking the event loop:** Never call synchronous I/O (DB queries, file reads) directly in event handlers. Always use `@work(thread=True)` for I/O-bound work
- **Direct Rich Console usage in TUI:** Don't use `console.print()` inside Textual apps. Use widget `.write()`, `.update()`, or reactive attributes instead
- **Modal overuse:** The user explicitly wants inline expand for inspection, not modals. Reserve ModalScreen only for the help overlay and confirm dialogs
- **Tight coupling to presentation:** Keep all business logic in existing modules. TUI screens should only call into `auto_triage()`, `execute_deletions()`, etc. -- never duplicate logic
- **Manual theme color hardcoding:** Use `$error`, `$success`, `$warning`, `$accent` CSS variables, not raw hex colors. Map TIER_COLORS to theme variables in TCSS

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tab navigation | Custom key handler + visibility toggle | Textual modes + BINDINGS | Modes handle screen stacks, focus, lifecycle automatically |
| Progress tracking | Custom percentage renderer | `ProgressBar` widget | Built-in ETA, percentage, animation |
| Log output | Custom scrolling text widget | `RichLog` widget | Auto-scroll, Rich renderable support, max_lines |
| Multi-select list | Custom checkbox + list combo | `SelectionList` or DataTable with manual toggle tracking | Built-in select/deselect_all, events |
| Sparkline charts | Unicode string builder (report.py has one) | `Sparkline` widget | Color interpolation, responsive sizing, reactive data |
| Theme switching | Manual color reassignment | `self.theme = "name"` + registered themes | Textual auto-regenerates all CSS variables |
| Toast notifications | Custom popup widget | `self.notify()` | Built-in positioning, timeout, severity levels |
| Keyboard help | Custom text overlay | `ModalScreen` with keybinding table | Auto-dismiss, backdrop, clean z-ordering |
| Scrollable tables | Custom rendering loop | `DataTable` widget | Sort, cursor, Rich cell styling, virtual scrolling |

**Key insight:** Textual provides nearly every UI component needed for this TUI out of the box. The primary work is wiring existing business logic into Textual event handlers and laying out widgets with TCSS.

## Common Pitfalls

### Pitfall 1: Blocking the Main Thread
**What goes wrong:** Calling `open_db()`, `scan_messages()`, `load_checkpoint()`, or `execute_deletions()` directly in `on_mount()` or event handlers freezes the UI
**Why it happens:** Textual's event loop is single-threaded asyncio. Synchronous I/O blocks all rendering and input
**How to avoid:** Always use `@work(thread=True)` for any function that does file I/O or DB access. Use `self.call_from_thread()` to update widgets from worker threads
**Warning signs:** UI becomes unresponsive during data loading, no progress updates

### Pitfall 2: Widget Updates from Wrong Thread
**What goes wrong:** Modifying widget attributes directly from a thread worker causes race conditions or crashes
**Why it happens:** Textual widgets are not thread-safe. Only the main event loop thread should modify widget state
**How to avoid:** Use `self.call_from_thread(widget.method, args)` or `self.app.call_from_thread()` from thread workers. For async workers, direct updates are safe
**Warning signs:** Intermittent rendering glitches, `RuntimeError` about event loop

### Pitfall 3: CSS Specificity Conflicts
**What goes wrong:** Widget styles don't apply, or wrong theme colors appear
**Why it happens:** Textual CSS follows web-like specificity rules. ID selectors override class selectors, etc.
**How to avoid:** Use a consistent naming convention (`#screen-widget` pattern). Keep per-screen TCSS files separate. Use `!important` sparingly
**Warning signs:** Widgets appear unstyled or with wrong colors despite CSS rules

### Pitfall 4: DataTable Performance with Large Datasets
**What goes wrong:** Slow rendering when loading thousands of cluster rows
**Why it happens:** DataTable renders visible rows efficiently but adding thousands of rows synchronously blocks
**How to avoid:** Pre-aggregate data before loading into DataTable. ~24k emails should be grouped into ~30-100 clusters, which DataTable handles easily. If showing individual emails (inspect mode), limit visible rows or use pagination
**Warning signs:** Slow initial load when switching to review screen

### Pitfall 5: Screen State Loss on Mode Switch
**What goes wrong:** Review progress (selections, scroll position) lost when switching between modes
**Why it happens:** By default, Textual recreates screen when entering a mode
**How to avoid:** Use `install_screen()` to pre-install screens, or store state in the App instance (shared data model). Review session is already persisted to disk via `save_session()`
**Warning signs:** User switches to Dashboard and back, losing their review position

### Pitfall 6: Rich Console Markup in Textual
**What goes wrong:** `[bold]text[/bold]` markup doesn't render in widgets
**Why it happens:** Not all widgets support Rich markup by default. `RichLog` needs `markup=True`, `Static` supports it, but DataTable cells need `Text` objects
**How to avoid:** Use `Rich.Text` objects for styled DataTable cells. Set `markup=True` on RichLog. For Static widgets, markup works by default
**Warning signs:** Raw markup brackets visible in output

## Code Examples

### Dashboard Screen Composition
```python
# Source: Textual layout guide + project requirements
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Sparkline, ProgressBar

class DashboardScreen(Screen):
    CSS_PATH = "dashboard.tcss"

    BINDINGS = [
        ("a", "auto_triage", "Auto-Triage"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="dashboard-content"):
            yield Static(id="storage-banner")  # "Potential savings: X GB (N emails)"
            with Horizontal(id="tier-panels"):
                yield TierSummaryWidget(id="tier-summary")
                yield PipelineStatusWidget(id="pipeline-status")
        yield Footer()
```

### Review Screen with Split View
```python
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, DataTable, Static

class ReviewScreen(Screen):
    CSS_PATH = "review.tcss"

    BINDINGS = [
        ("space", "toggle_select", "Select"),
        ("a", "approve_selected", "Approve"),
        ("s", "skip_selected", "Skip"),
        ("i", "inspect", "Inspect"),
        ("question_mark", "app.push_screen('help')", "Help"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="review-split"):
            with Vertical(id="left-panel"):
                yield Static("Clusters", id="list-header")
                yield DataTable(id="cluster-table", cursor_type="row")
                with Horizontal(id="bulk-actions"):
                    yield Button("Auto-Triage", id="btn-triage", variant="primary")
                    yield Button("Approve All", id="btn-approve", variant="error")
                    yield Button("Skip All", id="btn-skip", variant="success")
            with VerticalScroll(id="right-panel"):
                yield ClusterDetailWidget(id="cluster-detail")
        yield Footer()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail panel when cluster selection changes."""
        if event.row_key:
            detail = self.query_one("#cluster-detail", ClusterDetailWidget)
            detail.show_cluster(event.row_key.value)
```

### Execute Screen with Live Progress
```python
from textual import work
from textual.worker import get_current_worker
from textual.widgets import ProgressBar, RichLog, Static

class ExecuteScreen(Screen):
    CSS_PATH = "execute.tcss"

    @work(exclusive=True, thread=True)
    def run_execution(self, dry_run: bool = True) -> None:
        worker = get_current_worker()
        log = self.query_one("#exec-log", RichLog)
        progress = self.query_one("#exec-progress", ProgressBar)
        stats = self.query_one("#exec-stats", Static)

        # Reuse existing executor
        from icloud_cleanup.executor import ActionLog, execute_deletions

        approved = self._get_approved_messages()
        total = len(approved)
        self.call_from_thread(progress.update, total=total)

        success = 0
        errors = 0
        for batch_idx in range(0, total, 100):
            if worker.is_cancelled:
                self.call_from_thread(log.write, "[yellow]Cancelled[/yellow]")
                return
            batch = approved[batch_idx:batch_idx + 100]
            result = execute_deletions(batch, ...)
            success += result["success_count"]
            errors += result["error_count"]
            self.call_from_thread(progress.update, advance=len(batch))
            self.call_from_thread(
                stats.update,
                f"Success: {success} | Errors: {errors}"
            )
```

### TCSS Theme Color Mapping
```css
/* app.tcss - Map TIER_COLORS to Textual CSS */
.tier-trash { color: $error; }
.tier-keep-active { color: $success; }
.tier-keep-historical { color: $accent; }
.tier-review { color: $warning; }

/* Storage banner */
#storage-banner {
    height: 3;
    content-align: center middle;
    text-style: bold;
    background: $panel;
    margin: 1 2;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Textual < 1.0 CSS | Textual 8.x TCSS with themes | 2025 (v5/v6/v8 releases) | Theme system, improved CSS variables, registered themes |
| `push_screen`/`pop_screen` only | Modes (named screen stacks) | Textual 0.x | Better multi-section app architecture |
| Manual thread management | `@work` decorator | Textual 0.18+ | Cleaner worker lifecycle, auto-cancel |
| questionary prompts | Textual event handlers + widgets | N/A (paradigm shift) | Event-driven vs sequential prompt flow |
| Rich Console.print() | Widget.update() / RichLog.write() | N/A (paradigm shift) | Composable reactive UI vs imperative output |

**Deprecated/outdated:**
- Textual < 5.0: Many API changes in v5-v8 range. Use v8.0.2 docs exclusively
- `textual.reactive.Reactive` decorator: Replaced by simpler `reactive` attribute syntax in modern Textual
- `textual-dev` package: Dev tools now bundled in main `textual` package

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/test_tui.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map

Phase 4 has no formal requirement IDs in REQUIREMENTS.md (noted as TBD). Tests map to the implementation decisions from CONTEXT.md:

| Decision | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| TUI-01 | App launches, shows dashboard | unit | `pytest tests/test_tui.py::test_app_launches -x` | No - Wave 0 |
| TUI-02 | Mode switching D/R/E/P works | unit | `pytest tests/test_tui.py::test_mode_switching -x` | No - Wave 0 |
| TUI-03 | Dashboard shows tier summary | unit | `pytest tests/test_tui.py::test_dashboard_tier_summary -x` | No - Wave 0 |
| TUI-04 | Review cluster list loads | unit | `pytest tests/test_tui.py::test_review_cluster_list -x` | No - Wave 0 |
| TUI-05 | Review detail updates on selection | unit | `pytest tests/test_tui.py::test_review_detail_updates -x` | No - Wave 0 |
| TUI-06 | Bulk select and approve | unit | `pytest tests/test_tui.py::test_bulk_approve -x` | No - Wave 0 |
| TUI-07 | Execute screen shows progress | unit | `pytest tests/test_tui.py::test_execute_progress -x` | No - Wave 0 |
| TUI-08 | Pipeline worker runs in background | unit | `pytest tests/test_tui.py::test_pipeline_worker -x` | No - Wave 0 |
| TUI-09 | Theme toggle works | unit | `pytest tests/test_tui.py::test_theme_toggle -x` | No - Wave 0 |
| TUI-10 | Help overlay opens/closes | unit | `pytest tests/test_tui.py::test_help_overlay -x` | No - Wave 0 |
| TUI-11 | CLI 'tui' subcommand wiring | unit | `pytest tests/test_tui.py::test_cli_tui_subcommand -x` | No - Wave 0 |
| TUI-12 | Session interop (TUI saves, CLI reads) | integration | `pytest tests/test_tui.py::test_session_interop -x` | No - Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_tui.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tui.py` -- all TUI tests (new file)
- [ ] `tests/fixtures/test_checkpoint.jsonl` -- small test checkpoint for TUI tests (or generate in conftest)
- [ ] `pyproject.toml` update: add `pytest-asyncio` to dev deps, add `asyncio_mode = "auto"` to pytest config
- [ ] `pyproject.toml` update: add `textual` to dependencies

## Open Questions

1. **Textual v8 API stability**
   - What we know: v8.0.2 released March 2026. v5/v6/v7/v8 had breaking changes
   - What's unclear: Whether specific widget APIs (Sparkline, SelectionList) changed in v8
   - Recommendation: Pin `textual>=8.0,<9.0` in dependencies. Check widget imports work after install

2. **DataTable multi-select behavior**
   - What we know: DataTable supports cursor_type="row" and row selection events. SelectionList provides checkbox-style multi-select
   - What's unclear: Whether DataTable natively supports Space-to-toggle multi-select (user's desired interaction)
   - Recommendation: Either (a) use DataTable with manual selection tracking via a `set[str]` of selected row keys and custom key binding, or (b) embed a SelectionList for the cluster list. Option (a) is more flexible for the split-pane layout. Implement selection state as a reactive set on the screen

3. **Pipeline worker thread vs async**
   - What we know: Pipeline involves CPU-heavy work (embeddings, clustering) and I/O (DB, file parsing). `@work(thread=True)` runs in thread pool
   - What's unclear: Whether MLX GPU operations work correctly from a Textual thread worker
   - Recommendation: Use `@work(thread=True)` since existing pipeline code is synchronous. MLX operations are process-isolated (ProcessPoolExecutor in cmd_analyze). The thread worker just orchestrates

## Sources

### Primary (HIGH confidence)
- [Textual official docs - Screens](https://textual.textualize.io/guide/screens/) - Modes, push_screen, switch_screen patterns
- [Textual official docs - Workers](https://textual.textualize.io/guide/workers/) - @work decorator, thread workers, cancellation
- [Textual official docs - Design/Themes](https://textual.textualize.io/guide/design/) - Theme system, CSS variables, dark/light
- [Textual official docs - CSS](https://textual.textualize.io/guide/CSS/) - Layout, selectors, specificity
- [Textual official docs - Testing](https://textual.textualize.io/guide/testing/) - Pilot API, run_test, snapshot testing
- [Textual official docs - Layout Guide](https://textual.textualize.io/how-to/design-a-layout/) - Docking, fr units, containers
- [Textual official docs - DataTable](https://textual.textualize.io/widgets/data_table/) - Cursor types, events, methods
- [Textual official docs - Sparkline](https://textual.textualize.io/widgets/sparkline/) - Data format, summary_function, colors
- [Textual official docs - RichLog](https://textual.textualize.io/widgets/rich_log/) - write(), auto_scroll, markup
- [Textual official docs - SelectionList](https://textual.textualize.io/widgets/selection_list/) - Multi-select, events
- [Textual official docs - TabbedContent](https://textual.textualize.io/widgets/tabbed_content/) - Tabs, TabPane, events
- [PyPI textual 8.0.2](https://pypi.org/project/textual/) - Latest version, Python >=3.9 support

### Secondary (MEDIUM confidence)
- [Textual blog - 2025 posts](https://textual.textualize.io/blog/archive/2025/) - Release notes, new features
- [Textual GitHub](https://github.com/Textualize/textual) - Source, examples, discussions

### Tertiary (LOW confidence)
- None -- all findings verified with official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Textual 8.0.2 verified on PyPI, official docs comprehensive
- Architecture: HIGH - Modes, workers, widget patterns all documented with examples
- Pitfalls: HIGH - Common issues well-documented in official guides and GitHub discussions

**Research date:** 2026-03-05
**Valid until:** 2026-04-05 (Textual is actively developed but v8 API should be stable)
