# Domain Pitfalls

**Domain:** On-device iCloud email classification and cleanup tool
**Researched:** 2026-03-04

## Critical Pitfalls

Mistakes that cause data loss, rewrites, or major trust issues.

### Pitfall 1: False Positive Deletion — Trashing Personally Meaningful Emails

**What goes wrong:** The classifier marks a real email from a friend, old colleague, or important transactional sender as trash. Because sender-based grouping batches everything from a sender together, one bad group-level decision wipes out dozens of valuable emails. The user only discovers this weeks later when searching for something they can't find.

**Why it happens:** Sender-level classification treats all emails from a sender identically. But the same sender address can carry both junk and valuable content (e.g., `noreply@apple.com` sends both marketing AND purchase receipts). The v1 code's `NOREPLY_PATTERNS` list includes `hello@`, `team@`, `info@`, `support@` — all of which are used by real humans at small companies. A friend's startup using `hello@theircompany.com` gets nuked.

**Consequences:** Irreversible data loss if trash is emptied. Destroys trust in the tool. Undermines the core value proposition ("zero false positives on personally meaningful emails").

**Prevention:**
1. Never classify at the sender level alone. Require content-level signals (embeddings, behavioral patterns) to confirm.
2. Maintain a "personal signal" detector: any email that was replied to, forwarded, or from a sender the user has sent mail to at least once = unconditionally protected.
3. Apply asymmetric cost thresholds: the confidence required to trash (0.95+) must be far higher than to keep (0.5+). When in doubt, route to Review, never Trash.
4. The `NOREPLY_PATTERNS` approach from v1 is dangerous — `hello@`, `team@`, `info@`, `support@` should NOT be treated as no-reply indicators. Only `noreply@`, `no-reply@`, `do-not-reply@`, `mailer-daemon@`, and `bounce@` are safe bets.
5. Before executing any trash operation, show the user a sample of N emails from each group and require explicit confirmation.

**Detection:** Track false positive rate during development by manually labeling a test set of 200-500 emails and measuring precision on the Trash class. If precision on Trash < 99%, the classifier is not safe to deploy.

**Phase:** Must be addressed in Phase 1 (classification design). The entire classification architecture should be built around asymmetric error costs.

---

### Pitfall 2: Same-Sender Mixed Content — Transactional vs. Marketing from One Address

**What goes wrong:** Many companies send both transactional emails (purchase receipts, shipping confirmations, password resets) and marketing emails from the same sender address or domain. Sender-level grouping forces a single classification on mixed-value content.

**Why it happens:** The v1 approach groups by sender address and assigns one dominant category to the group. If `noreply@amazon.com` sends 80 marketing emails and 20 order confirmations, the dominant category is "Promotions" and the group gets marked for trash — including the order confirmations.

**Consequences:** Loss of receipts, shipping info, account security emails. Particularly dangerous for financial/legal records that share sender addresses with marketing content.

**Prevention:**
1. Classify at the individual message level, not the sender-group level. Sender reputation is an input signal, not the final decision.
2. Use content embeddings to distinguish transactional from promotional content within the same sender.
3. Build a "transactional keyword" safeguard: emails containing patterns like "order confirmation", "receipt", "password reset", "security alert", "two-factor", "billing statement" get unconditional protection regardless of sender classification.
4. Present groups in the report but allow per-message overrides in the review flow.

**Detection:** During testing, examine the top 20 senders by volume and manually verify that each group doesn't contain mixed-value content. If any do, the grouping strategy needs refinement.

**Phase:** Phase 1 (classification design) and Phase 2 (content analysis with embeddings).

---

### Pitfall 3: AppleScript Execution is Fragile, Slow, and Unreliable at Scale

**What goes wrong:** The v1 code uses AppleScript via `osascript` to move messages to trash. AppleScript's Mail.app interface is slow (each batch requires Mail to parse, find, and move messages), unreliable (timeout errors, account name mismatches, mailbox naming inconsistencies), and creates IMAP sync overhead that can hang Mail for minutes.

**Why it happens:** AppleScript in Mail.app was designed for small-scale automation, not batch operations on thousands of messages. Each `move` triggers an IMAP command to the server, which can throttle or fail. The v1 code matches messages by ROWID (`id is {m.rowid}`), but AppleScript's `id` property for messages may not correspond to the SQLite ROWID — this is an undocumented assumption that could silently target wrong messages.

**Consequences:** Moves the wrong emails, timeouts leave operations half-complete (some messages moved, others not), Mail.app becomes unresponsive, IMAP sync corruption.

**Prevention:**
1. Validate the AppleScript `id` property mapping: before any batch operation, verify that AppleScript's message `id` matches the SQLite ROWID by cross-referencing a small sample (query a message by ROWID, get its subject/date, then find it via AppleScript and confirm).
2. Process in small batches (25-50 messages, not 100) with verification between batches.
3. Implement a pre-execution manifest: write a JSON file listing every message to be trashed (subject, sender, date, message_id) so the user can review and so recovery is possible.
4. Consider alternative execution strategies: using `mailutil` command-line tool, or manipulating the `mailbox` column in the Envelope Index directly (risky but faster), or using PyObjC to interact with Mail.app's Objective-C bridge.
5. Add a post-execution verification step: re-query the database to confirm messages actually moved.

**Detection:** If any batch takes > 30 seconds or returns fewer moved messages than expected, halt and report the discrepancy.

**Phase:** Phase 4 (execution/deletion). This is the highest-risk phase.

---

### Pitfall 4: Envelope Index Database Locking and Corruption

**What goes wrong:** Reading the Envelope Index while Mail.app is running can encounter WAL (Write-Ahead Logging) locks, return stale data, or in worst case corrupt the database. The v1 code correctly uses `?mode=ro` URI for read-only access, but there are edge cases where even read-only connections fail.

**Why it happens:** Apple Mail uses SQLite WAL mode. A read-only connection to a WAL database requires the `-shm` and `-wal` files to exist and be readable. If Mail has an exclusive lock (during heavy sync operations, migration, or indexing), read queries can return `SQLITE_BUSY`. More critically, if the WAL file is being checkpointed during a read, results may be inconsistent.

**Consequences:** Tool crashes with "database is locked" errors, or worse, returns incomplete/stale data leading to wrong classification decisions (e.g., missing recently-received important emails).

**Prevention:**
1. Keep the v1 pattern: always open as `?mode=ro` with URI mode. Never open in read-write mode.
2. Add retry logic with exponential backoff for `SQLITE_BUSY` errors (3 retries, 1s/2s/4s).
3. Check if Mail.app is in an active sync/indexing state before scanning (look for the "Checking for Mail" status or simply warn the user to let sync complete first).
4. Validate data completeness after loading: compare message count against a known baseline or against `mailboxes` table metadata.
5. Never write to the Envelope Index. Even "harmless" writes (like adding an index for performance) can break Mail.app or trigger a full re-index.

**Detection:** Log the connection time and query time. If any query takes > 10 seconds, Mail likely has a lock. If message count is 0 or dramatically different from expected (~25K), data load is incomplete.

**Phase:** Phase 1 (data access layer). Must be rock-solid before any classification work begins.

---

### Pitfall 5: Envelope Index Schema is Undocumented and Can Change Between macOS Versions

**What goes wrong:** The Envelope Index schema has no official documentation, no foreign key constraints, and Apple changes it across macOS versions without notice. Table names, column names, or relationships that work on Sequoia may not exist on the next macOS release. The `message_global_data` table (used for `model_category`) was added relatively recently.

**Why it happens:** Apple considers the Envelope Index an internal implementation detail. The V10 folder has remained stable through Sonoma and Sequoia, but each OS upgrade can trigger a migration that rebuilds the database with schema changes. Forums report upgrade failures where the Envelope Index must be deleted and rebuilt from scratch.

**Consequences:** Tool breaks silently after a macOS update. Queries return zero rows or crash with "no such column" errors. If schema changes are subtle (e.g., `date_received` interpretation changes), classification produces garbage without any visible error.

**Prevention:**
1. Add a schema validation step at startup: check that expected tables and columns exist. If any are missing, abort with a clear error message instead of producing wrong results.
2. Query `PRAGMA table_info(messages)` and `PRAGMA table_info(message_global_data)` to verify column names.
3. Store the expected schema version or a hash of the schema as a config constant, and warn when it changes.
4. Do not rely on `model_category` exclusively since v2's whole point is to replace Apple's classification — but if you use it as a signal, gracefully handle it being NULL or missing entirely.
5. Pin the tool to a known-working macOS version in the README and test after each macOS update.

**Detection:** The schema validation at startup catches this. Also, if `get_icloud_messages()` returns 0 messages when the mailbox is known to have ~25K, something is wrong with the query.

**Phase:** Phase 1 (data access layer). Schema validation should be the first thing the tool does.

## Moderate Pitfalls

### Pitfall 6: MLX Model Loading Cold Start Kills Interactive UX

**What goes wrong:** Loading an embedding model into GPU memory via MLX takes 5-15 seconds depending on model size. If the tool loads the model fresh for every run (or worse, for every batch), the user waits forever.

**Why it happens:** MLX downloads model weights from Hugging Face Hub on first use, then loads them into unified memory. Even from disk cache, deserializing a 100MB+ model is not instant. The `mlx-embeddings` library loads lazily, so the first `generate()` call is slow.

**Prevention:**
1. Load the model once at the start of the scan, before processing any emails.
2. Use a smaller model for initial triage (e.g., `all-MiniLM-L6-v2` at ~80MB) — larger models rarely justify the overhead for email classification.
3. Show a progress indicator during model loading ("Loading embedding model...").
4. Consider pre-downloading the model during installation (`uv run python -c "from mlx_embeddings import ..."`) to avoid surprises on first run.
5. Batch all embeddings in one pass rather than embedding messages one at a time.

**Detection:** If the tool takes > 20 seconds before showing any output, model loading is the bottleneck.

**Phase:** Phase 2 (content analysis / MLX integration).

---

### Pitfall 7: Email Subject Lines are Too Short for Reliable Embedding Classification

**What goes wrong:** Many emails have subjects like "Re:", "Hi", "(no subject)", "Order #12345", or single-word subjects. Sentence embeddings produce low-quality vectors for very short text, leading to unreliable cosine similarity scores and garbage classification.

**Why it happens:** Embedding models are trained on sentences and paragraphs, not 3-word email subjects. The average email subject is ~60 characters. Short-text embeddings cluster poorly in vector space — "Hi" from a friend and "Hi" from spam end up with nearly identical embeddings.

**Consequences:** Low-confidence classifications that either route too much to Review (useless tool) or misclassify (dangerous tool).

**Prevention:**
1. Combine subject + sender + first ~200 characters of body text into a single input string for embedding. Format as: `"From: {sender} | Subject: {subject} | {body_preview}"`.
2. For subject-only analysis (when body text isn't available from the Envelope Index), supplement with sender reputation and behavioral signals rather than relying on embedding quality.
3. Set minimum text length thresholds: if combined text is < 20 characters, skip embedding and rely entirely on non-content signals (sender frequency, read status, reply history).
4. Reading `.emlx` files for body text is the solution but adds I/O overhead — batch reads and cache results.

**Detection:** Monitor the embedding confidence distribution. If > 30% of messages have confidence scores in the 0.4-0.6 range (near the decision boundary), the embedding signal is too weak.

**Phase:** Phase 2 (content analysis). Architecture decision on whether to read `.emlx` bodies or use metadata-only.

---

### Pitfall 8: Behavioral Signals (Read/Replied/Ignored) Are Incomplete or Misleading

**What goes wrong:** The tool uses read status and reply history as classification signals, but these signals are noisy. Many people read junk emails out of curiosity. Many important emails are never replied to. Bulk-marking as read doesn't indicate engagement.

**Why it happens:** "Read" status only means the email was displayed in the preview pane, not that the user intentionally engaged with it. Reply history is stored in the Envelope Index `flags` column as bitmasks, but the specific bit values are undocumented and may vary. The `in_reply_to` field links replies but doesn't capture replies sent from other clients or webmail.

**Consequences:** Behavioral signals add noise instead of signal, degrading classification accuracy.

**Prevention:**
1. Treat "read" as a weak signal (small weight). Treat "replied to" as a strong signal (high weight) — replying requires intentional action.
2. For reply detection, check both `in_reply_to` in the messages table AND look for outbound messages to the same address in the Sent mailbox.
3. Never use "unread" as evidence for trash — people routinely leave newsletters unread while valuing them.
4. "Ignored" (unread for > 30 days in inbox) is a moderate trash signal but only in combination with other signals.
5. Document the `flags` bitmask values by empirical testing: mark a test email as read/unread/replied/forwarded and observe which bits change.

**Detection:** A/B test classification with and without behavioral signals on the labeled test set. If behavioral signals don't improve accuracy by at least 2-3%, they're adding noise and should be dropped or re-weighted.

**Phase:** Phase 2 (signal engineering). Requires empirical validation.

---

### Pitfall 9: The `.emlx` File System Layout Is Fragile and Non-Obvious

**What goes wrong:** To read email bodies, you need to parse `.emlx` files from disk. But the file system layout under `~/Library/Mail/V10/` is complex: messages are stored in UUID-named account folders, with numeric subfolder sharding, and the mapping from Envelope Index ROWID to the correct `.emlx` file path is not straightforward.

**Why it happens:** Apple Mail stores messages as `{message_id}.emlx` (or `{message_id}.partial.emlx` for messages with attachments) inside mailbox folders named with UUIDs. The path includes the account UUID, the mailbox UUID, and a sub-folder for message sharding. The Envelope Index doesn't store the full file path — you have to reconstruct it from `mailboxes.url` and the message identifier.

**Consequences:** File-not-found errors for messages that exist in the database but whose `.emlx` files were deleted or moved during a sync. Parsing failures due to the `.emlx` format (byte count prefix, LF line endings, plist trailer). Attachments split across `.emlxpart` files.

**Prevention:**
1. Build a robust path resolver: `mailboxes` table has a `path` column that, combined with the message ROWID, gives you the file system location. Verify this mapping empirically.
2. Handle missing `.emlx` files gracefully — metadata-only fallback when the file doesn't exist.
3. Parse `.emlx` files defensively: read the byte count from the first line, extract only that many bytes as the RFC 5322 message, ignore the trailing plist (or parse it separately for flags/metadata).
4. Skip `.emlxpart` / attachment files entirely — body text doesn't require attachments.
5. Cache parsed body text to avoid re-reading `.emlx` files on subsequent runs.

**Detection:** If > 5% of Envelope Index messages have no corresponding `.emlx` file, the path resolution logic is wrong.

**Phase:** Phase 2 (content analysis). Only needed if reading email bodies for embeddings.

---

### Pitfall 10: Confidence Score Calibration — Raw Similarity is Not Probability

**What goes wrong:** The tool uses cosine similarity from embeddings as a "confidence score" and presents it to the user as though 0.85 means "85% confident this is trash." But cosine similarity is not a calibrated probability. A similarity of 0.85 to a "trash" centroid might correspond to 60% true probability, while 0.70 might correspond to 95% for a different cluster.

**Why it happens:** Embedding similarity operates in a different mathematical space than probability. The distribution of similarity scores depends on the model, the data, and the cluster density. Without calibration, thresholds chosen by intuition ("0.8 seems high enough") will produce unpredictable error rates.

**Consequences:** Users see "95% confidence" and trust it, but the actual false positive rate could be 10%. Or the threshold is set too conservatively and everything routes to Review, making the tool useless.

**Prevention:**
1. Calibrate confidence scores using a labeled validation set. Fit a sigmoid or Platt scaling function that maps raw similarity to true probability.
2. If you can't build a labeled set large enough, use percentile-based thresholds instead of absolute thresholds: "top 5% most similar to trash cluster = auto-trash, next 10% = review, rest = keep."
3. Display confidence scores as categories (High/Medium/Low) rather than percentages to avoid false precision.
4. Report calibration metrics in the output: "Of the N messages classified as Trash with High confidence, here are 5 random samples for spot-checking."

**Detection:** Plot a reliability diagram (predicted confidence vs. actual accuracy) on the validation set. If the curve deviates significantly from the diagonal, calibration is needed.

**Phase:** Phase 3 (confidence scoring and calibration).

## Minor Pitfalls

### Pitfall 11: iCloud UUID Hardcoded and May Change

**What goes wrong:** The v1 code hardcodes `ICLOUD_UUID = "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"`. This UUID identifies the iCloud account in the Envelope Index. If Javi re-adds the iCloud account, does a clean macOS install, or migrates to a new Mac, the UUID changes and the tool silently returns zero messages.

**Prevention:** Auto-detect the iCloud account UUID by querying `mailboxes` for URLs containing `@icloud` or `@me.com` patterns, or by finding the account whose type matches iCloud. Fall back to the hardcoded UUID as a last resort and warn if auto-detection fails.

**Phase:** Phase 1 (data access layer).

---

### Pitfall 12: Claude API Usage for Ambiguous Cases Leaks Email Content

**What goes wrong:** The project spec calls for using Claude API for low-confidence edge cases. Sending email content (subject, body, sender) to an external API violates the "all processing on-device" privacy promise.

**Prevention:**
1. Be explicit about what gets sent: only subject + sender, never full body text.
2. Add a `--no-api` flag that disables external API calls entirely, routing everything to Review instead.
3. Log every API call with the exact payload so the user can audit what was sent.
4. Consider whether a small local LLM (via MLX) could handle ambiguous cases instead, keeping everything on-device.

**Phase:** Phase 3 (hybrid ML). Must be opt-in, not default.

---

### Pitfall 13: Deduplication by Message-ID is Not Foolproof

**What goes wrong:** Emails can exist in multiple mailboxes (Inbox + Archive, or Inbox + a custom folder). Deduplicating by `message_id` seems safe but has edge cases: draft emails lack Message-IDs, some mailers generate duplicate IDs, and case sensitivity of IDs varies.

**Prevention:**
1. Use the Envelope Index ROWID as the unique identifier for operations (it's unique per row regardless of message_id).
2. For deduplication in classification, group by `(message_id, mailbox)` to handle the same message in multiple folders.
3. When trashing, only trash from the Inbox — leave Archive/Sent copies untouched.

**Phase:** Phase 1 (data modeling).

---

### Pitfall 14: Rate of Emails Being Classified Outpaces User's Ability to Review

**What goes wrong:** The tool produces a report with hundreds of sender groups and thousands of individual classifications. The user doesn't have time to review them all, so they either approve everything blindly (defeating the safety purpose) or abandon the tool (wasted effort).

**Prevention:**
1. Prioritize the review queue: show only the groups where the classification is uncertain or where stakes are highest (e.g., senders with both trash and keep signals).
2. Use progressive disclosure: first show only Trash groups (the ones where the user's approval is needed for deletion), then show Review groups, then summarize Keep groups.
3. Provide bulk approval UX: "Approve all Trash groups matching: promotional, no-reply, > 50 emails, zero replies" as a single action.
4. Limit the report to actionable items — the user doesn't need to see 500 "keep" groups.

**Phase:** Phase 3 (interactive review/report UX).

---

### Pitfall 15: Memory Pressure When Embedding 25K+ Emails in a Single Pass

**What goes wrong:** Loading 25K email texts into memory and generating embeddings for all of them in one batch can exhaust available RAM, especially if body text is included. MLX unified memory means GPU and CPU compete for the same pool.

**Prevention:**
1. Process in batches of 256-512 texts. Generate embeddings, store results, free the batch, repeat.
2. Store embeddings to disk (numpy `.npy` or SQLite blob) rather than keeping all 25K vectors in memory.
3. For the M1 Max with 32GB unified memory, a batch of 512 short texts (~100 tokens each) with a MiniLM model should use < 1GB. But monitor with `mx.metal.get_active_memory()` or `psutil`.
4. If using body text, truncate to first 256 tokens per email — the classification signal is in the opening, not the footer.

**Phase:** Phase 2 (MLX integration). Test with real data volume early.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-|-|-|
| Data access (Phase 1) | DB locking, schema changes, hardcoded UUID | Schema validation at startup, auto-detect UUID, retry logic for BUSY errors |
| Classification design (Phase 1) | Same-sender mixed content, false positive deletion | Per-message classification, asymmetric cost thresholds, reply-based protection |
| Content analysis (Phase 2) | Short-text embedding quality, .emlx parsing, model cold start | Combined subject+sender+body input, small model choice, batch processing |
| Behavioral signals (Phase 2) | Read/replied signals are noisy | Empirical validation, weight replies >> reads, ignore "unread" for trash |
| Confidence scoring (Phase 3) | Uncalibrated similarity scores | Labeled validation set, percentile-based thresholds, avoid fake precision |
| Review UX (Phase 3) | Review queue too large for user | Progressive disclosure, bulk approval, prioritize uncertain groups |
| Execution (Phase 4) | AppleScript unreliable, wrong message targeting, IMAP sync issues | Verify ID mapping, small batches, pre-execution manifest, post-execution check |
| Privacy (Cross-phase) | Claude API leaking email content | Opt-in only, subject-only payloads, audit logging, local LLM alternative |

## Sources

- [Mail.app Database Schema](https://labs.wordtothewise.com/mailapp/) - Undocumented schema reference
- [Parsing EMLX files](https://gist.github.com/karlcow/5276813) - EMLX format gotchas
- [EMLX File Format Analysis](https://www.mailxaminer.com/blog/emlx-file-format/) - Forensic analysis of EMLX structure
- [SQLite WAL Mode Documentation](https://sqlite.org/wal.html) - Read-only connection behavior in WAL mode
- [SQLite Concurrent Writes](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) - Database locking deep dive
- [EDRM Message ID Hash for Deduplication](https://www.relativity.com/blog/introducing-the-edrm-message-id-hash-simplify-cross-platform-email-duplicate-identification/) - Message-ID reliability issues
- [Classification Threshold Tuning](https://www.evidentlyai.com/classification-metrics/classification-threshold) - Asymmetric cost and calibration
- [Supervised Methods for Email Classification](https://www.tandfonline.com/doi/full/10.1080/21642583.2025.2474450) - Literature survey of email classification pitfalls
- [Text Sequence Classification with MLX](https://wormtooth.com/20250308-text-sequence-classification-with-apple-mlx/) - MLX classification implementation
- [Batch Moving Emails in Apple Mail](https://www.macscripter.net/t/batch-moving-emails-in-apple-mail/73203) - AppleScript performance issues
- [Deep Dive Into Filing Mail via AppleScript](https://msgfiler.wordpress.com/2024/02/12/a-deep-dive-into-filing-mail-messages-using-applescript/) - AppleScript message ID mapping
- [Apple Mail Upgrading to Sequoia Crashes](https://discussions.apple.com/thread/255810571) - Schema migration risks
- [MLX-Embeddings GitHub](https://github.com/Blaizzy/mlx-embeddings) - Batch processing API
- [Qwen3 Embeddings MLX](https://github.com/jakedahn/qwen3-embeddings-mlx) - Performance benchmarks on Apple Silicon
- [Email Intent Detection with Embeddings](https://dl.acm.org/doi/10.1145/3325291.3325357) - Subject vs. body text for classification
- [Transactional vs Marketing Emails](https://www.mailersend.com/help/transactional-email-vs-marketing-email) - Same-sender mixed content problem
