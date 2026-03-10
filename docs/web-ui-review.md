# Web UI Review — Multi-Discipline Audit

**Date:** 2026-03-09
**Disciplines consulted:** Interface Design, UI/UX Pro Max, Graphic Designer, UX Heuristics, Frontend Design

---

## The User & Context

**Who:** Javi — power user triaging 2,500+ emails on a MacBook. Focused, sustained work. ADHD brain — UI must minimize cognitive load and maximize flow state.

**Task:** Binary decisions (trash/keep) at speed, with ability to zoom in on edge cases.

**Feel:** Mission control terminal — dense, efficient, no wasted space, but clear enough that you never wonder "what did I just do?"

---

## CRITICAL Issues (Fix These)

| # | Issue | Discipline | Severity |
|-|-|-|-|
| 1 | **No loading/feedback states** — clicking anything gives zero visual feedback until data arrives. No skeleton screens, no spinners, no optimistic updates. | UX Heuristics (Nielsen #1: Visibility of System Status) | 4/4 |
| 2 | **Keyboard navigation is nonexistent** — no focus rings on table rows, no `j/k` to move between emails, no shortcuts for trash/keep. For a triage tool, this is a massive speed bottleneck. | UX Heuristics, Interface Design | 3/4 |
| 3 | **No confirmation toast on bulk actions** — "Delete entire cluster" fires silently. You see the result but get no confirmation like "47 emails marked for deletion." Undo exists per-row but is easy to miss. | UX Heuristics (Nielsen #1, #3) | 3/4 |
| 4 | **Decision counts in header are confusing** — `individual_trash` and `individual_keep` exclude cluster-level decisions. The progress bar tracks clusters but the numbers track emails. Mixed units create cognitive dissonance. | UX Heuristics (Nielsen #2: Match Real World) | 3/4 |

---

## HIGH-Priority Improvements

| # | Issue | What to Do | Discipline |
|-|-|-|-|
| 5 | **Sidebar has no search/filter** — with 50+ clusters, scrolling to find one by name is painful. Add a filter input at top of sidebar. | UX Heuristics (Nielsen #7: Flexibility) |
| 6 | **Cluster sidebar shows too little info at a glance** — the confidence range text `0.45–0.92` is hard to scan. Replace with a tiny inline sparkline or colored confidence dot (red/yellow/green). | Graphic Designer (visual hierarchy), Interface Design |
| 7 | **No "done" momentum feedback** — in a 2,500-email triage session, you need dopamine. Show a running count like "1,247 / 2,500 decided" with a ring or arc that fills. The current progress bar only tracks clusters, not individual email decisions. | Interface Design (signature element), UX Heuristics |
| 8 | **Email table lacks row density toggle** — 13px font with 8px padding is comfortable but slow for power-user scanning. Offer compact mode (11px, 4px padding) that doubles visible rows. | UI/UX Pro Max, Interface Design |
| 9 | **View tabs + sender toggle create dual navigation** — "By sender" sits in the tab bar but behaves completely differently (switches entire view mode vs. filtering). This breaks Nielsen #4 (Consistency). Move sender view into a proper split with its own icon/treatment. | UX Heuristics, Interface Design |
| 10 | **Expanded email row has no inline actions** — you expand a row to read the body, then have to close it and use the checkbox + bulk bar to decide. Add trash/keep buttons directly in the expanded row. | UX Heuristics (Nielsen #7), Graphic Designer |

---

## MEDIUM-Priority Refinements

| # | Area | Current | Proposed | Why |
|-|-|-|-|-|
| 11 | **Typography** | System font stack (`-apple-system`) | Keep system stack for body. Add `font-variant-numeric: tabular-nums` globally to all numeric columns, not just `.conf`. | UI/UX Pro Max — tabular nums prevent layout jitter when numbers change |
| 12 | **Color tokens** | `--red`, `--green`, `--yellow` | Rename to semantic tokens: `--destructive`, `--safe`, `--warning`. Keeps intent clear, makes future theming trivial. | Interface Design (token architecture) |
| 13 | **Border treatment** | `1px solid var(--border)` everywhere — every element has identical border weight | Introduce a second border level: `--border-subtle` at lower opacity for table rows, keep `--border` for section dividers. Currently too many lines competing. | Interface Design (border progression), Graphic Designer (visual noise) |
| 14 | **Sidebar vs content background** | Sidebar uses `--surface`, content area uses `--bg` | Interface Design skill explicitly says: "Sidebars: same background as canvas, not different." The color difference fragments the visual space. Use same bg + border separation only. | Interface Design |
| 15 | **Tier labels** | Raw text: `trash`, `keep_active`, `keep_historical`, `review` | These are internal system terms. Humanize: "Delete", "Active", "Historical", "Review". The underscore is a code smell in UI. | UX Heuristics (Nielsen #2: Match Real World) |
| 16 | **Sender view has no pagination** | Renders all senders in one scroll | For 500+ unique domains, this will lag. Add virtual scrolling or pagination. | UI/UX Pro Max (performance) |
| 17 | **No empty state design** | "No emails match filters" plain text | Add a clear illustration/icon + suggestion to broaden filters. Empty states are a chance to guide. | UX Heuristics (Nielsen #10: Help) |
| 18 | **Guide banner is too wordy** | 4 steps, ~40 words each | Cut to single-line per step. "1. Pick cluster -> 2. Filter -> 3. Decide -> 4. Execute." Get rid of half the words, then half again. | UX Heuristics (Krug's Law #3) |

---

## LOW-Priority Polish (But High Impact on Feel)

| # | What | Details |
|-|-|-|
| 19 | **Add micro-transitions** | Rows entering/leaving should fade. Expanded row should slide open (max-height transition). Currently everything pops in/out instantly — feels brittle. 150ms ease-out is enough. |
| 20 | **Sticky bulk bar should float, not sit inline** | The bulk bar currently pushes content down. Pin it as a floating bar at the bottom of the viewport (above pagination) so the table doesn't reflow. |
| 21 | **Decision badges need more contrast** | `rgba(255,107,107,0.2)` on `#0f1117` background is very low contrast. Bump to 0.3 and test. |
| 22 | **Add `prefers-reduced-motion` media query** | Required for accessibility. Wrap all `transition` and any future `animation` in `@media (prefers-reduced-motion: no-preference)`. |
| 23 | **Domain filter dropdown is stale** | The domain dropdown rebuilds on every `loadEmails()` but doesn't persist the selected value reliably when data changes. Should be a static list fetched once. |

---

## What to REMOVE

| What | Why |
|-|-|
| **DOMPurify CDN script** | Not used — all rendering uses `textContent` (safe DOM). Dead dependency adds 15KB and a CDN dependency for zero benefit. |
| **"Decide later" button on cluster actions** | Redundant. Not deciding IS deciding later. The button writes a "skip" decision which is actually a "keep" action — confusing semantics. Just remove it. |
| **The `approve`/`skip` internal terminology leaking into the UI** | `data-view="approve"` and `data-view="skip"` are backend terms. The tab says "Marked for deletion" but the value is "approve" — this creates bugs when someone reads the code. Map to `delete`/`keep` in the frontend. |

---

## What to ADD (New Features)

| Feature | Rationale | Effort |
|-|-|-|
| **Keyboard shortcuts overlay** | `?` to show shortcuts, `j/k` for row navigation, `d` for delete, `k` for keep, `u` for undo, `Enter` to expand. This is a triage tool — keyboard is faster than mouse. | Medium |
| **Session timer** | Show how long you've been triaging. Helps with ADHD time-blindness. Small clock in the header. | Small |
| **Quick stats bar** | Between the view tabs and filters, show: "Avg confidence: 0.73 | Top domain: newsletter.com (342) | Est. time remaining: ~12 min". Contextual info for the current view. | Medium |
| **"Mark rest as keep" button** | After triaging borderline cases, you want to say "everything I haven't touched, keep it." One button, massive time-saver. | Small |
| **Toast notification system** | Non-blocking toast at bottom-right: "47 emails from example.com marked for deletion. Undo" with auto-dismiss after 5s. Replaces the need for confirmation dialogs. | Small |

---

## Architecture Notes

The entire UI is a single 1,300-line HTML file. This works for now, but any further features should consider:
- Extracting CSS into a separate `style.css` (cacheable)
- Breaking JS into modules with `<script type="module">` if the file grows past ~1,500 lines
- The state object is a plain global — fine for this scale, but reactive state (even a simple pub/sub) would reduce manual DOM sync bugs

---

## Recommended Implementation Order

1. **Toast system + feedback states** (fixes #1, #3) — biggest UX gap
2. **Keyboard shortcuts** (#2, new feature) — biggest speed gain
3. **Inline actions in expanded row** (#10) — removes friction
4. **Unified progress metric** (#4, #7) — fixes confusion
5. **Sidebar cluster search** (#5) — quality of life
6. **Rename tier labels + remove internal terminology** (#15, remove #3) — polish
7. **Everything else** in severity order
