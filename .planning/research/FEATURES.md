# Feature Landscape

**Domain:** Email cleanup and intelligent classification tool (local/on-device, privacy-first)
**Researched:** 2026-03-04

## Table Stakes

Features users expect from any email cleanup tool. Missing = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Sender-based grouping | Every tool (Clean Email, Cleanfox, GoodByEmail) groups by sender. Users think about email in terms of "who sent it." | Low | Envelope Index has sender data readily available. Group by domain and individual address. |
| Bulk operations | Users expect to act on hundreds/thousands at once, not one-by-one. Clean Email processes 100k+ simultaneously. | Low | Core value prop. Trash/archive/keep applied per group, not per message. |
| Volume statistics | GoodByEmail shows email count per sender, storage consumed, last received date. Users need data to make decisions. | Low | Query Envelope Index for count, date range, size per sender/domain. |
| Dry run / preview mode | Users won't trust a tool that deletes without showing what it'll do first. Every credible tool has preview. | Low | `--report` mode before `--execute`. Already in v1 design. Non-negotiable. |
| Undo / reversibility | Cleanfox has reverse button. Clean Email has Action History. Users need a safety net. | Low | Trash (not permanent delete) + log of what was trashed with timestamps. Restore script. |
| Unsubscribe detection | Cleanfox, Leave Me Alone, and Clean Email all identify subscription emails. Table stakes for cleanup. | Medium | Detect List-Unsubscribe header in .emlx files. Flag but don't auto-unsubscribe (out of scope for local tool). |
| Read/unread awareness | Basic signal every tool uses. Unread bulk mail = obvious cleanup candidate. | Low | Available in Envelope Index `messages` table (read flag). |
| Category/type detection | Clean Email has 30+ smart views (social, shopping, finance, newsletters). Users expect some automated grouping beyond just sender. | Medium | Build lightweight heuristics from sender domain patterns + subject keywords. Don't need 30 categories -- 8-10 covers 90%. |
| Progress reporting | With 25k+ emails, users need to know scanning isn't frozen. Especially for ML-heavy processing. | Low | Progress bar with count/total, ETA. Rich terminal output via `rich` library. |

## Differentiators

Features that set this tool apart from Clean Email, SaneBox, Cleanfox, etc. These are the reasons to build this instead of using an existing product.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **100% local/on-device processing** | GoodByEmail is the only competitor doing local processing, and it only analyzes metadata. This tool does full content analysis via MLX embeddings without any data leaving the machine. No OAuth, no cloud, no IMAP connection. Privacy is absolute. | Medium | Key differentiator vs. every cloud-based competitor. Leverages M1 Max GPU. |
| **Multi-signal classification (4-tier)** | SaneBox uses headers only. Clean Email uses metadata only. This tool combines: (1) sender reputation from contact/reply history, (2) content semantics via embeddings, (3) behavioral signals (read/replied/ignored), (4) temporal patterns. Four classification tiers (Trash/Active/Historical/Review) capture nuance that binary spam/ham can't. | High | Core innovation. No competitor combines all four signal types locally. |
| **Confidence scoring with explanations** | No consumer tool shows *why* it classified an email. This tool assigns a 0-1 confidence score and lists which signals contributed. Transparency builds trust for aggressive cleanup. | Medium | Critical for the "zero false positive" goal. Low-confidence items route to Review tier automatically. |
| **Historical/sentimental email protection** | No competitor explicitly protects old personal emails. SaneBox only cares about recency. An email from a college friend in 2013 you never replied to would be trashed by any existing tool. This tool uses contact reputation + content analysis to identify personally meaningful emails regardless of age or engagement. | High | Core value prop per PROJECT.md: "email archive is a data asset." Requires embedding-based content understanding to distinguish personal from transactional. |
| **Behavioral signal analysis** | Read status, reply history, deletion patterns, time-to-open. SaneBox analyzes some header-level behavior but only for future filtering. This tool retroactively analyzes 15 years of behavior to score every email's importance. | Medium | Envelope Index has read/flagged/replied metadata. Rich signal for classification. |
| **Contact reputation scoring** | Beyond simple "known sender" checks. Score each contact based on: bidirectional communication (you replied?), frequency, recency, relationship type (personal vs. commercial), and cross-reference with address book. | Medium | Distinguishes "newsletter you subscribed to" from "person you know." SaneBox does domain-level analysis; this is per-contact with reply-history depth. |
| **Interactive terminal walkthrough** | Not just a report dump. Category-by-category approval flow in the terminal with examples, stats, and confidence distributions. User reviews each classification group before any action executes. | Medium | `rich` + `questionary` or similar. Most tools are GUI-only or batch-only. Interactive CLI is a sweet spot for power users. |
| **Hybrid ML (local + API fallback)** | MLX handles 95%+ of classification at zero cost. Claude API only invoked for genuinely ambiguous cases (low embedding confidence, mixed signals). Budget-conscious and privacy-respecting. | Medium | Most tools are either fully cloud or fully rule-based. Hybrid approach is novel for this domain. |
| **Semantic content clustering** | Group emails by meaning, not just sender. MLX embeddings can identify that 500 emails from different senders are all "shipping notifications" or "password resets." Enables cleanup of patterns that span multiple senders. | High | Differentiator over all metadata-only tools. Requires embedding computation over .emlx body text. GPU-accelerated on M1 Max. |

## Anti-Features

Features to explicitly NOT build. Each has a clear reason to avoid.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **IMAP connection / server-side operations** | Adds network complexity, rate limiting, authentication headaches, risk of modifying server state. Local DB is faster and safer. | Read Envelope Index SQLite + .emlx files directly. All data is already synced locally by Apple Mail. |
| **Automatic unsubscribe execution** | Requires sending HTTP requests or emails on user's behalf. Privacy/trust risk. Many unsubscribe links are phishing vectors. Some require login. | Detect and flag List-Unsubscribe headers. Show user the unsubscribe URL. Let them act manually. |
| **Ongoing mail filtering / rules** | Turns a cleanup tool into a mail client. Scope creep. SaneBox and Clean Email own this space with IMAP integration. | One-time classification and cleanup. If user wants ongoing filtering, recommend SaneBox. |
| **GUI / web interface** | Adds massive complexity (framework, state management, hosting). Target user (Javi) is CLI-comfortable. Cloud GUI would undermine privacy story. | Rich terminal UI with `rich` library. Colored output, tables, progress bars, interactive prompts. |
| **Multi-account support** | Scope creep for v2. Different accounts have different Envelope Index paths, different contact histories. | Single account (user@icloud.com). Architecture should not prevent future multi-account, but don't build it now. |
| **Data selling / anonymized analytics** | Unroll.Me's entire business model. Directly contradicts privacy-first positioning. Even "anonymized" data is ethically questionable. | Zero data exfiltration. All processing on-device. No telemetry, no analytics, no phone-home. |
| **Apple Mail category labels as input** | The whole point of this project. Apple Intelligence categories are unreliable -- 36% uncategorized, frequent miscategorization. | Build independent classification from raw signals (sender, content, behavior). Apple categories are the problem, not the solution. |
| **Permanent deletion** | Irreversible. One false positive = lost email forever. No amount of confidence scoring justifies this. | Move to Trash only. Apple Mail's Trash auto-purges after 30 days. User can recover anything within that window. |
| **Email content forwarding to cloud APIs** | Sending full email bodies to any API (even Claude) violates privacy-first principle for bulk processing. | MLX embeddings run locally. Claude API receives only metadata summaries for ambiguous cases, never full email bodies. |
| **Real-time / daemon mode** | Not needed for a cleanup tool. Adds process management, crash recovery, resource monitoring complexity. | Run on-demand via CLI. User triggers scan, reviews report, approves actions. |

## Feature Dependencies

```
Envelope Index scanning ──> Volume statistics
                       ──> Read/unread awareness
                       ──> Sender-based grouping ──> Category/type detection
                       ──> Contact reputation scoring ──> Multi-signal classification

.emlx file parsing ──> Unsubscribe detection (List-Unsubscribe header)
                  ──> Content embedding (MLX) ──> Semantic content clustering
                                              ──> Historical email protection
                                              ──> Multi-signal classification

Behavioral signal extraction ──> Multi-signal classification

Multi-signal classification ──> Confidence scoring
                           ──> 4-tier assignment (Trash/Active/Historical/Review)
                           ──> Cleanup report generation

Cleanup report generation ──> Interactive terminal walkthrough ──> Bulk operations (execute)
                                                               ──> Undo/reversibility (trash log)

Progress reporting (independent -- wraps any long-running operation)
```

**Critical path:** Envelope Index scanning > sender grouping > contact reputation > behavioral signals > classification > report > interactive review > execute.

**Parallel work possible:** .emlx parsing + embedding can run alongside Envelope Index analysis. They converge at the classification stage.

## MVP Recommendation

**Phase 1 -- Scan and classify without ML (table stakes + deterministic signals):**

1. Envelope Index scanning with volume statistics
2. Sender-based grouping with domain categorization
3. Contact reputation scoring (reply history, frequency, recency)
4. Behavioral signal extraction (read/replied/ignored/deleted)
5. Deterministic classification using weighted scoring of above signals
6. Dry run report with confidence scores
7. Progress reporting

**Phase 2 -- Add ML classification (differentiators):**

8. .emlx content parsing and MLX embedding generation
9. Semantic content clustering
10. Historical/sentimental email protection via embedding analysis
11. Hybrid confidence scoring (deterministic + embedding signals)
12. Claude API fallback for low-confidence cases

**Phase 3 -- Interactive execution:**

13. Interactive terminal walkthrough (category-by-category review)
14. Bulk operation execution (trash approved categories)
15. Undo/reversibility (action log + restore script)

**Defer:**
- Unsubscribe detection: Nice to have but not core to cleanup workflow. Add after Phase 3.
- Semantic clustering visualization: Interesting but not actionable. Defer indefinitely.
- Multi-account: Out of scope per PROJECT.md constraints.

**Rationale:** Phase 1 delivers a working tool that's already better than Apple Mail's categorization. Phase 2 adds the ML differentiator that no competitor has locally. Phase 3 makes it safe to actually execute. Each phase produces usable output.

## Competitive Landscape Summary

| Tool | Processing | Signals Used | Privacy | Cost | Limitation for This Use Case |
|------|-----------|-------------|---------|------|------------------------------|
| **Clean Email** | Cloud (IMAP) | Metadata only (sender, subject, date) | OAuth required, claims no content reading | $30/yr | No content analysis, requires IMAP, cloud-dependent |
| **SaneBox** | Cloud (IMAP) | Headers + user behavior training | No email body access | $7-36/mo | Ongoing filtering focus, not bulk cleanup. No retroactive analysis. |
| **Cleanfox** | Cloud (IMAP) | Sender frequency, open rate | OAuth required | Free | Shallow analysis, no content understanding, no historical protection |
| **Unroll.Me** | Cloud (IMAP) | Subscription detection | **Sells data to Rakuten** | Free | Massive privacy violation. Banned in EU (GDPR). |
| **Leave Me Alone** | Cloud (IMAP) | Subscription detection | Privacy-focused, no data selling | Pay-per-use | Unsubscribe only, no classification |
| **GoodByEmail** | **Local** | Metadata only (sender, size, date) | No OAuth, no cloud | Freemium | Metadata only -- no content analysis, no behavioral signals, no ML |
| **This tool** | **Local** | **Sender + content + behavior + temporal** | **No OAuth, no cloud, no IMAP** | Free (OSS) | Single account, CLI only, one-time cleanup (not ongoing) |

The closest competitor is GoodByEmail for local processing, but it only does metadata analysis. No existing tool combines local ML content analysis with behavioral signals for retroactive email classification.

## Sources

- [Clean Email features](https://clean.email/features) -- feature breakdown, smart views, auto clean
- [Clean Email review 2026](https://work-management.org/productivity-tools/clean-email-review/) -- detailed feature analysis
- [SaneBox AI organization guide](https://www.digitoolsadvice.com/2026/02/how-sanebox-uses-ai-to-organize-and.html) -- classification signals
- [SaneBox help: features](https://www.sanebox.com/help/138-what-is-a-feature) -- folder system details
- [SaneBox help: advanced filtering](https://www.sanebox.com/help/116-what-is-advanced-filtering) -- filtering approach
- [GoodByEmail](https://www.goodbyemail.com/) -- privacy-first local processing approach
- [GoodByEmail story](https://www.eskinasy.com/goodbyemail/the-story-behind-goodbyemail/) -- motivation and architecture
- [Leave Me Alone](https://leavemealone.com/) -- privacy-focused unsubscribe
- [Unroll.Me privacy concerns 2025](https://removeonlineinformation.com/blog/unroll-me-privacy-concerns-2025/) -- data selling practices
- [Cleanfox](https://www.cleanfox.io/) -- swipe-based cleanup features
- [Email classification with word embeddings](https://link.springer.com/article/10.1007/s00521-020-05058-4) -- ML approaches
- [ML spam filtering survey](https://pmc.ncbi.nlm.nih.gov/articles/PMC6562150/) -- classification techniques
- [Best email cleaner apps 2026](https://clean.email/blog/email-management/best-email-cleaner-app) -- competitive landscape
- [Superhuman email cleaner comparison](https://blog.superhuman.com/app-to-clean-up-email/) -- tool comparison
