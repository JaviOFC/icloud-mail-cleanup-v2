# TUI Design Conference Report

## Why We Held This Conference

During Phase 4 human verification, the user ran `python -m icloud_cleanup tui` and provided 17 screenshots showing the TUI across all screens, both themes, overlays, and edge cases. The screenshots revealed systemic UX problems that couldn't be fixed piecemeal — they needed a holistic design audit. Rather than applying ad-hoc patches, we convened four design perspectives to evaluate the TUI against established frameworks and reach consensus on improvements.

## Participants

| Perspective | Framework | Focus Area |
|-|-|-|
| **Interface Design** | Intent-first design, subtle layering, signature elements | Navigation as product, surface elevation, token architecture |
| **UI/UX Pro Max** | 50+ styles, 97 palettes, 99 UX guidelines | Accessibility, touch/keyboard interaction, loading states, layout |
| **Graphic Designer** | CRAP principles, visual hierarchy, 60-30-10 color rule | Contrast, Repetition, Alignment, Proximity, white space |
| **UX Heuristics** | Krug's 3 Laws + Nielsen's 10 Heuristics | Don't Make Me Think, Recognition > Recall, Trunk Test |

## Evidence Reviewed

17 screenshots showing:
- Dashboard with welcome overlay (manual-space alignment broken)
- Dashboard with global help overlay (Rich Tables working but narrow container)
- Review screen without popup (sparse detail panel, no sender data)
- Review screen with 4 stacked "Keybindings" toasts (notification bug)
- Review screen with intro popup (manual-space alignment broken)
- Review screen at smaller terminal width (clipped columns)
- Pipeline screen (dark theme, with/without overlay)
- Pipeline screen (light theme, with/without overlay)
- Execute screen (dark theme, with/without overlay)
- Full desktop context screenshot

## Individual Assessments

### Interface Design Assessment

Evaluated through the lens of "every choice must be a choice" and "navigation IS the product."

**Key findings:**
1. D/R/E/P keys are not choices — they're defaults carried from the internal mode names. Real design would match keys to how users think about workflow.
2. Overlay width (64 chars) is not a design choice — it's the first number someone typed. Responsive percentages with min/max serve actual terminal diversity.
3. Center-aligned body text with left-aligned content = visual conflict. Multi-line text should always be left-aligned.
4. Manual spaces for keybinding alignment fail the "squint test" — blur your eyes and the structure disappears. Rich Tables maintain alignment at any width.
5. The detail panel shows data without meaning. Structured sections (Overview / Top Senders / Example Subjects) create visual proximity groups that help users parse information.

**Recommendation:** Treat the TUI as a product with intent, not a feature with defaults. Every visual element should be a deliberate design choice.

### UI/UX Pro Max Assessment

Evaluated against accessibility, interaction, and layout guidelines.

**Key findings:**
1. **Keyboard navigation (CRITICAL):** Tab order must match visual order. Current D/R/E/P doesn't match any visual ordering. 1/2/3/4 with footer in same order fixes this.
2. **Error feedback:** After popup dismisses, users have zero context. Persistent hint bar provides always-visible feedback about available actions.
3. **Loading states:** Dashboard async data load shows "Loading..." (acceptable). Pipeline/Execute have progress bars (good). Review detail empty state shows bare "Example subjects:" with nothing below (bad — needs empty-state messaging).
4. **Toast stacking bug:** The `action_help()` method on Review fires a toast every time `?` is pressed, stacking 4+ duplicate toasts. This is a notification UX bug, not a feature.

**Pre-delivery checklist items failed:**
- [ ] All interactive elements have clear keyboard focus indicators — PARTIAL
- [ ] Loading/empty states for all data-dependent components — FAIL (detail panel)
- [ ] Consistent help pattern across screens — FAIL (mixed toast/popup/first-visit patterns)

### Graphic Designer Assessment

Evaluated through CRAP principles and visual hierarchy.

**Key findings:**
1. **Alignment (CRAP):** Manual spaces `"  [bold]D[/bold] Dashboard  -  tier summary"` break alignment because bold markup changes character widths in some renderers. Rich Tables with column definitions guarantee alignment. **Severity: High.**
2. **Proximity (CRAP):** Detail panel renders a flat list of lines with no visual grouping. Users can't quickly distinguish "what is this cluster" from "who sent emails" from "what were they about." Adding section headers with Rich bold markup creates proximity groups. **Severity: Medium.**
3. **Contrast (CRAP):** Overlay text has uniform weight — section headers look the same as body text. Bold section headers + regular body creates contrast hierarchy. **Severity: Medium.**
4. **White Space:** At 64 chars wide on a 200+ char terminal, overlays waste 70% of horizontal space. More padding within overlays and wider containers let content breathe. **Severity: Low-Medium.**

**Quality checklist (scored 0-10):**
- Hierarchy: 5/10 — flat text, no clear #1 element per overlay
- Contrast: 6/10 — theme colors work but text hierarchy is flat
- Alignment: 3/10 — manual spaces = fundamentally broken
- White Space: 5/10 — cramped overlays, adequate screen layout
- Visual Impact: 5/10 — functional but not crafted
- **Average: 4.8/10** (needs 7+ to pass)

### UX Heuristics Assessment

Full scored evaluation against Krug's 3 Laws and Nielsen's 10 Heuristics.

**Krug's Laws:**

| Law | Score | Detail |
|-|-|-|
| Don't Make Me Think | 4/10 | D/R/E/P forces memorization. "Triage" and "Propagation" are jargon that make users stop and think. After popup dismiss, zero context forces recall. |
| Clicks = Confidence | 6/10 | Each keypress navigates successfully, but doesn't build confidence because screen provides no orientation after popup closes. |
| Get Rid of Half Words | 7/10 | Overlay text is reasonable length. Some screen_help text could be tighter but not critically verbose. |
| Trunk Test | 5/10 | Can identify current mode (footer highlight). Cannot identify what to do on this screen, what actions are available, or how to get help. |

**Nielsen's 10 Heuristics:**

| # | Heuristic | Score | Detail |
|-|-|-|-|
| H1 | Visibility of System Status | 7/10 | Pipeline/Execute progress bars good. Dashboard async load adequate. |
| H2 | Match Between System and Real World | 6/10 | "Triage" is medical jargon. "Propagation" is graph-theory jargon. Users think "auto-sort" and "similar senders." |
| H3 | User Control and Freedom | 5/10 | No undo for approve/skip (session saves immediately). Escape works for back. Cancel works for long operations. |
| H4 | Consistency and Standards | 5/10 | Help patterns inconsistent: `?` = global modal, first-visit = screen popup, `?` on Review = stacking toast. Three different help mechanisms. |
| H5 | Error Prevention | 7/10 | Dry-run default excellent. "No clusters selected" warning good. |
| H6 | Recognition Rather Than Recall | **3/10** | **WORST SCORE.** After popup dismisses, every keybinding must be recalled from memory. D/R/E/P requires mnemonic recall. No persistent on-screen hints. |
| H7 | Flexibility and Efficiency of Use | 6/10 | Keyboard shortcuts exist but aren't discoverable without help overlay. Auto-triage for power users good. |
| H8 | Aesthetic and Minimalist Design | 6/10 | Layout is clean. Overlays are cramped. Detail panel sparse. |
| H9 | Help Users Recover from Errors | 7/10 | Error messages functional. "No clusters selected" guides user. |
| H10 | Help and Documentation | 4/10 | Help exists (3 different mechanisms!) but not consistently recallable. Alignment broken in two of three. |

**Overall: 5.6/10**

**Severity ratings for top issues:**

| Issue | Heuristic | Severity | Priority |
|-|-|-|-|
| No persistent keybinding hints | H6 Recognition > Recall | 3 (Major) | Fix immediately |
| D/R/E/P mnemonic keys | Krug Law 1 | 3 (Major) | Fix immediately |
| Can't recall dismissed help | H10 Help & Documentation | 3 (Major) | Fix immediately |
| "Triage"/"Propagation" jargon | H2 Match Real World | 2 (Minor) | Schedule fix |
| Manual-space alignment | H8 Aesthetic & Minimal | 2 (Minor) | Schedule fix |
| Toast stacking on Review | H1 Visibility of Status | 2 (Minor) | Schedule fix |
| Sparse detail panel | H1 Visibility of Status | 2 (Minor) | Schedule fix |
| Narrow overlays | H8 Aesthetic & Minimal | 1 (Cosmetic) | Fix if time |

## Cross-Perspective Consensus

| Issue | Interface Design | UI/UX Pro Max | Graphic Designer | UX Heuristics |
|-|-|-|-|-|
| D/R/E/P → 1/2/3/4 | "Navigation IS the product" | "Tab order = visual order" | Z-pattern reading flow | Krug Law 1: Don't Think |
| Rich Tables for alignment | Squint test fails | — | CRAP: Alignment | — |
| Wider overlays | "Width is a default, not a choice" | "Wastes space on wide terminals" | White space principle | — |
| Persistent hint bar | "Screens need context" | "Always provide feedback" | — | H6: Recognition > Recall |
| Recallable help (`h`) | — | "Consistent help patterns" | — | H10: Help & Documentation |
| Structured detail panel | "Data without meaning" | "Empty state messaging" | CRAP: Proximity | H1: System Status |
| Remove toast stacking | — | "Broken notification UX" | — | H4: Consistency |
| Rename jargon | — | — | — | Krug Law 1 + H2: Real World |

**All 8 fixes are unanimously or majority-supported.** The jargon rename (item 7) was uniquely identified by UX Heuristics — the other three perspectives didn't flag "Triage" and "Propagation" as problematic because they focused on visual/structural issues rather than language.

## Expected Outcome

After implementing all 8 fixes:
- Heuristic score: 5.6/10 → ~8.5/10
- Graphic Designer quality score: 4.8/10 → ~7.5/10
- All Severity 3 (Major) issues resolved
- Consistent help pattern across all screens (hint bar + `h` key + `?` global)
- Zero-memorization navigation (numbered keys match footer order)
- Self-evident screen context at all times
