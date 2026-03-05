---
created: 2026-03-05T05:15:20.457Z
title: Import macOS Contacts to refine known-sender detection
area: general
files:
  - src/icloud_cleanup/contacts.py
---

## Problem

The classifier currently determines "known contacts" solely from Envelope Index data (bidirectional email exchanges, reply history). This misses contacts the user knows but hasn't emailed via iCloud — e.g., contacts added manually, synced from phone, or only emailed from other accounts.

macOS Contacts.app stores contacts in an AddressBook SQLite database (`~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb`) or via the Contacts framework. Importing these email addresses would strengthen the contact_score signal and protect more real contacts from being trashed.

## Solution

Options to explore:
1. **SQLite direct read** — Query the AddressBook database for email addresses (read-only, same pattern as Envelope Index). Path: `~/Library/Application Support/AddressBook/` or `~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb`
2. **`contacts` CLI tool** — Check if there's a macOS command-line tool or AppleScript bridge to export contacts
3. **Python `pyobjc` bindings** — Use `Contacts.framework` via PyObjC to enumerate contacts programmatically

Integration: Add a `load_system_contacts() -> set[str]` function that returns known email addresses. Feed into `build_contact_profiles()` to boost contact_score for addresses found in the system address book, even if no bidirectional email history exists.

This could move some emails from Trash/Review to Keep for contacts the user knows but doesn't email via iCloud.
