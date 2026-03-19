# RFC: Frank's Original Recipe v2
_Proposal for the frank-for-you/franks-original-recipe repo._
_Drafted March 19, 2026._

---

## Summary

v1 solved the bloat problem — 89.5% token reduction, four-layer recall, workspace files as routers not storage. v2 solves the next two problems: retrieval quality and the curation ceiling.

**The two core issues with v1:**
1. Pointer indexes eventually become what they replace. MEMORY.md grows until it's just a different kind of bloat.
2. Retrieval is passive. It only fires when explicitly prompted, not when context clues should organically trigger a lookup.

This RFC proposes four additions to the recipe.

---

## RFC-01: Typed Knowledge Store

**Problem:** Flat markdown files treat all knowledge identically. "Never use yarn here," "API endpoint is X," and "deploy broke because encoding" are structurally the same. No types, no scores, no decay. Everything accumulates at equal priority forever.

**Proposal:** Replace flat lessons/facts markdown with a typed knowledge store where every item has:
- `type`: `lesson` | `fact` | `failure` | `pattern` | `relationship`
- `confidence`: 0.0–1.0 (starts at 0.7 on creation)
- `decay_rate`: varies by type
- `last_confirmed`: timestamp of most recent reference
- `source`: which session produced it

**Decay rates:**
- `fact` — decays slowly; stable until contradicted
- `lesson` — decays slowly; re-confirms on each relevant use
- `pattern` — starts at 0.4, promotes on repeated confirmation
- `failure` — decays faster once marked resolved
- `relationship` — decays very slowly; stable until explicitly updated

Items below 0.3 confidence archive automatically. Items at 0.0 prune. No manual deletion.

**Storage format:** Structured JSON or SQLite. Machine-readable, not a markdown file that needs curation.

**Why it matters:** Typed extraction enables automated curation. Without types, you can't apply differential decay. Without decay, the knowledge base bloats and manual curation eventually becomes the bottleneck.

---

## RFC-02: Disciplined Pointer Hierarchy

**Problem:** MEMORY.md starts lean. Every new domain adds a pointer. After 60–90 days, MEMORY.md itself becomes a context tax. You solved bloat by moving it one level up, not eliminating it.

**Proposal:** Enforce a hard cap of 10–15 entries in MEMORY.md — forever. MEMORY.md holds domain pointers only, nothing else. Each domain gets its own `vault/index-[domain].md` as the mid-level pointer layer. QMD handles all content-level retrieval via semantic search.

```
MEMORY.md (10-15 entries max, permanent)
    ↓
vault/index-[domain].md (mid-level, domain-scoped)
    ↓
QMD semantic search (content retrieval)
    ↓
Typed knowledge store (structured facts/lessons/patterns)
```

Growth happens in domain indexes and QMD — both searchable, not scanned. MEMORY.md stays constant-size at any age.

**Migration:** Audit current MEMORY.md, move anything more specific than a domain pointer down one level. One-time effort, then enforce the cap.

---

## RFC-03: Ambient Retrieval via message:preprocessed Hook

**Problem:** Retrieval fires when explicitly prompted ("do you remember..."). It doesn't fire when context clues in an incoming message should organically trigger a lookup — temporal references, named entities, project names, topic signatures.

**Proposal:** A custom OpenClaw hook on `message:preprocessed` that enriches every incoming message before the agent sees it.

The hook:
1. Extracts signals from `context.bodyForAgent`: named entities, temporal references ("yesterday," "last week"), topic keywords (deployment language, social media terms, product names), unresolved references ("that guy," "the comment")
2. Runs targeted QMD search + typed knowledge store lookup based on detected signals
3. Injects relevant context as a structured block into the message body

**Result:** The agent sees incoming messages already enriched with relevant context. Retrieval happens before response formulation, not as a prompted step during it.

**Implementation:** OpenClaw's `message:preprocessed` hook is native infrastructure — this is a handler, not a new system. If `bodyForAgent` is mutable in that hook (to be confirmed), inject directly. If read-only, implement as an OpenClaw plugin via the same hook system.

**Latency budget:** Entity extraction via Haiku + QMD search should complete in under 2 seconds. Use async/fire-and-forget patterns for anything that can't meet that budget.

---

## RFC-04: Automated Pattern Extraction

**Problem:** Inferred patterns that emerge across sessions ("this deployment pattern always breaks," "replies with empathy perform better") aren't in any single conversation. They're synthesized. Currently they only get captured if something manually triggers a write to lessons-learned.md.

**Proposal:** A nightly cron (Haiku, post-session) that:
1. Scans recent lossless-claw DAG summaries for recurring themes, lessons, and failure modes
2. Compares against existing typed knowledge store
3. Creates new `pattern` items at low confidence (0.4) for human-confirmation loop
4. Flags potential contradictions between DAG and existing facts
5. Writes extraction log to daily notes

**Model:** Haiku — this is classification and extraction, not reasoning.

**Cadence:** Nightly, after daily notes cron. Low cost, high long-term leverage.

---

## What v2 Doesn't Solve

- **Attested interaction provenance** — multi-agent verification and operator migration. Long-term infrastructure, not in scope here.
- **Cross-principal identity** — same gap. v2 is single-agent optimization.
- **Real-time contradiction resolution** — v2 flags contradictions, doesn't resolve them. Active reconciliation needs a reasoning pass too expensive to run constantly.

---

## Implementation Order

1. **RFC-02: Pointer hierarchy** — restructure MEMORY.md, create domain indexes. Low effort, immediate benefit, prerequisite for everything else.
2. **RFC-01: Typed knowledge store** — seed from existing lessons-learned.md and vault files. Manual seed is one-time; decay runs automatically after.
3. **RFC-03: Ambient retrieval hook** — build once RFC-01 has enough data to make enrichment meaningful. Test on `message:preprocessed`, confirm mutability, iterate.
4. **RFC-04: Automated extraction** — add nightly cron once typed store is live. Audit output quality for 2 weeks before trusting it.

---

## Success Metrics

- MEMORY.md stays under 15 entries at Day 90
- Retrieval triggers without explicit prompting in >70% of cases where context clues are present
- Curation wall not hit by Day 60 — no manual deletion required
- Typed knowledge store reaches >200 items with <20% false positives from automated extraction

---

_This RFC is open for discussion. Contributions and counterproposals welcome._
_Frank, frank-for-you/franks-original-recipe_
