---
created: 2026-03-05T05:15:20.457Z
title: Import macOS Contacts to refine known-sender detection
area: general
files:
  - src/icloud_cleanup/contacts.py
---

## Problem

The classifier determines "known contacts" solely from Envelope Index data (bidirectional email exchanges, reply history). This misses contacts the user knows but hasn't emailed via iCloud — e.g., doctors, accountants, schools, vendors added to Contacts manually or synced from phone.

These senders score contact_score=0.0 ("unknown sender") and get no protection. If they're also automated or high-volume (e.g., appointment reminders from a doctor's office), they land in Trash. This is the main false-positive risk: **Keep-Historical emails from real contacts miscategorized as Trash because the only contact signal comes from email exchange history.**

macOS Contacts.app stores contacts in a local SQLite database. Importing those email addresses would protect known contacts from being trashed even without bidirectional email history.

## Solution

Options to explore:
1. **SQLite direct read** — Query the AddressBook database for email addresses (read-only, same pattern as Envelope Index). Path: `~/Library/Application Support/AddressBook/` or `~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb`
2. **`contacts` CLI tool** — Check if there's a macOS command-line tool or AppleScript bridge to export contacts
3. **Python `pyobjc` bindings** — Use `Contacts.framework` via PyObjC to enumerate contacts programmatically

Integration: Add a `load_system_contacts() -> set[str]` function that returns known email addresses. Feed into `build_contact_profiles()` to boost contact_score for addresses found in the system address book, even if no bidirectional email history exists.

This could move some emails from Trash/Review to Keep for contacts the user knows but doesn't email via iCloud.
