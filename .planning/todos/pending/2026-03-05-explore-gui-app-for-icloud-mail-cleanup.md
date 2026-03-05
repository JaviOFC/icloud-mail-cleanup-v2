---
created: 2026-03-05T06:05:57.990Z
title: Explore GUI app for iCloud mail cleanup
area: general
files: []
---

## Problem

The tool is currently CLI-only (`python -m icloud_cleanup scan/classify`). A GUI would make it accessible as a standalone app — especially useful for the review step (Phase 3) where the user needs to inspect thousands of email classifications and approve/reject actions. Reviewing 6,000+ "review" tier emails in terminal output or CSV is painful.

## Solution

Research needed — key questions:

1. **Framework choice**: PyQt6/PySide6 (native feel, complex), Textual (TUI — terminal but rich), Tauri + web frontend (modern, lightweight binary), SwiftUI + Python bridge (most native but hardest), Electron (heaviest)
2. **Packaging**: py2app or PyInstaller for macOS .app bundle? Homebrew cask?
3. **Scope**: Full app vs. just a review/approval GUI that wraps the existing CLI pipeline?
4. **Data flow**: GUI reads checkpoint.jsonl + scan results, presents classification table with filters/search, user approves batches, triggers execution
5. **Effort estimate**: Minimal viable review UI vs. full management app — very different scopes
6. **Alternative**: Web UI (Flask/FastAPI + htmx) running locally — lighter than desktop app, still visual

This is a future-phase exploration, not blocking current work.
