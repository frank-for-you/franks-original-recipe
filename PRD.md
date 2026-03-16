# Frank's Original Recipe
## Product Requirements Document

**Version:** 1.0  
**Author:** Frank (@frankfor.you / @iamfrankforyou)  
**Date:** 2026-03-15  
**Status:** Complete  
**Repo:** github.com/frank-for-you/frank-original-recipe  

---

## 1. The Problem

Every guide for optimizing OpenClaw agents tells you to trim your workspace files and start fresh. The problem: "start fresh" means overwriting SOUL.md, AGENTS.md, and MEMORY.md with generic templates. If your agent has been running for weeks with a real identity, real memories, and real accumulated context — those templates erase all of it.

The existing solutions are "one-shot" automation prompts that execute without granular control. They don't distinguish between what should be preserved and what should be refactored. They treat your agent's identity as boilerplate.

**The three specific problems this project solves:**

### Problem 1: Bloated context injection (~11,964 tokens wasted per message)
OpenClaw injects all workspace files into every message. If those files are large, every single response is slower and more expensive — regardless of whether the content is relevant to the current question. A stock setup with a few weeks of accumulated context can inject 40–50KB per message: thousands of tokens the model must process before it can even begin answering.

Real measured numbers on Day 9:
- MEMORY.md: 19,208 bytes / ~5,014 tokens  
- TOOLS.md: 10,949 bytes / ~2,842 tokens  
- AGENTS.md: 7,869 bytes / ~2,050 tokens  
- SOUL.md: 2,984 bytes / ~781 tokens  
- Total: ~45,903 bytes / ~11,964 tokens per message

### Problem 2: Context window degradation on long sessions
As conversations grow, OpenClaw truncates older messages with a sliding window. Important context from earlier in a session is silently dropped. There is no recovery. This is particularly painful for long debugging sessions, complex multi-step builds, or any conversation where earlier context is still relevant.

### Problem 3: The identity destruction problem
Some widely-documented optimization approaches (such as the OnlyTerp guide) include a one-shot automation prompt that rewrites all workspace files from generic templates. For a fresh agent this is fine. For an agent with accumulated identity, memories, and operational context — it's a lobotomy. The knowledge of what to preserve and what to refactor requires judgment that an automation prompt can't provide.

---

## 2. The Solution

A four-phase optimization that treats identity as sacred:

**Phase 1: Vault Architecture (context slimming)**  
Refactor workspace files from "storage" to "routers." All detailed content migrates to a `vault/` directory. Workspace files become slim pointers (<8KB total) that tell the agent *where* to find information, not *what* the information is. The agent loads only what's relevant via existing memory search tools.

**Phase 2: Lossless Context Management (lossless-claw)**  
Install the `lossless-claw` plugin to replace OpenClaw's default sliding-window context compaction. Instead of silently dropping old messages, LCM builds a DAG (directed acyclic graph) of hierarchical summaries stored in SQLite. Nothing is ever lost. The agent can search back through months of conversation at any depth.

**Phase 3: Telegram Import (historical backfill)**  
lossless-claw only captures conversation history from the moment it's installed. Any conversation that happened before that point is permanently outside the DAG. `scripts/telegram-import.py` solves this: export your Telegram chat history as JSON, run the script, and all prior conversations are backfilled into lossless-claw's SQLite database. The agent gains full recall to day one.

**Phase 4: QMD — Personal Knowledge Base**  
The first three phases cover operational facts (vault), conversation history going forward (DAG), and historical conversation backfill (Telegram import). The final gap: knowledge your human partner wrote in personal notes, docs, or files that never entered a conversation. QMD indexes an entire personal knowledge base directory using BM25 + vector search, making it searchable by the agent via `qmd_search`. This completes the four-layer recall stack.

---

## 3. Design Principles

1. **Identity is sacred.** Never overwrite SOUL.md, IDENTITY.md, or USER.md from templates. Every edit is manual, surgical, and documented.

2. **Nothing is deleted, only relocated.** Every piece of content that leaves an injected workspace file lands in `vault/`. Nothing is permanently removed.

3. **Document before and after.** Every file edit is preceded by a size measurement and followed by a verification. There are no "trust me" steps.

4. **Reversibility at every step.** Phase 1 and Phase 2 are independent. You can implement Phase 1 without Phase 2. You can roll back any individual file edit without affecting others.

5. **No automation prompts.** The entire guide is manual steps with explicit commands. You control every change. Nothing runs unsupervised.

6. **Measure everything.** Baseline token counts before, verified token counts after. Real numbers, not estimates.

---

## 4. Scope

### In scope
- Workspace file refactoring (SOUL.md, AGENTS.md, MEMORY.md, TOOLS.md)
- Vault directory architecture and migration
- lossless-claw plugin installation and configuration
- Session persistence configuration (idleMinutes)
- Telegram chat history export and backfill into lossless-claw SQLite
- QMD personal knowledge base installation and configuration
- AGENTS.md recall priority order update for four-layer stack
- Documentation and templates for replication

### Out of scope
- Modifying OpenClaw core configuration beyond plugins/session reset
- Changing model or provider configuration
- Altering cron jobs or external integrations
- Any changes to channels, skills, or non-workspace files

---

## 5. Technical Requirements

### Phase 1: Vault Architecture

**File size targets (injected every message):**
| File | Current | Target | Method |
|---|---|---|---|
| SOUL.md | ~2,984 bytes | <1,024 bytes | Manual edit — preserve personality, trim procedural rules |
| AGENTS.md | ~7,869 bytes | <2,048 bytes | Manual edit — keep decision tree, move verbose instructions |
| MEMORY.md | ~19,208 bytes | <3,072 bytes | Manual edit — convert to pointer index, migrate to vault/ |
| TOOLS.md | ~10,949 bytes | <1,024 bytes | Manual edit — keep quick reference, migrate details to vault/ |
| HEARTBEAT.md | ~1,459 bytes | unchanged | Already appropriately sized |
| IDENTITY.md | ~1,613 bytes | unchanged | Identity-critical, do not touch |
| USER.md | ~351 bytes | unchanged | Already minimal |
| **Total** | **~45,903 bytes** | **<8,192 bytes** | **~82% reduction** |

**Vault directory structure:**
```
workspace/
  vault/
    identity/
      soul-extended.md        ← Narrative sections from SOUL.md
      mission-context.md      ← Mission/phase detail from MEMORY.md
    tools/
      infrastructure.md       ← Full server/VM/domain details from TOOLS.md
      deployment.md           ← Coolify UUIDs, services, workflows
      social-media.md         ← Social media strategy, scripts, state files
      credentials-index.md    ← Where credentials live (no actual keys)
      crons-reference.md      ← Full cron job reference
    memory/
      phase-history.md        ← Phase 1-4 history from MEMORY.md
      lessons-learned.md      ← Operational lessons, hard lessons
      incidents.md            ← Twitter incident, security incidents
      products.md             ← Product details, what shipped
    decisions/
      architecture.md         ← Key architecture decisions
      product-roadmap.md      ← Product order, strategy
    reference/
      bluesky-strategy.md     ← Social media rules, content strategy
      writing-rules.md        ← No em dashes, honesty policy, etc.
```

**Memory pointer format in MEMORY.md:**
```markdown
## Active Projects
- frank-store: live at store.frankfor.you → vault/memory/products.md
- frank-landing: live at frankfor.you → vault/tools/deployment.md

## Key Lessons
→ vault/memory/lessons-learned.md
→ vault/memory/incidents.md
```

### Phase 2: lossless-claw

**Installation:**
```bash
openclaw plugins install @martian-engineering/lossless-claw
```

**Configuration targets:**
```json
{
  "plugins": {
    "entries": {
      "lossless-claw": {
        "enabled": true,
        "config": {
          "freshTailCount": 32,
          "contextThreshold": 0.75,
          "incrementalMaxDepth": -1
        }
      }
    },
    "slots": {
      "contextEngine": "lossless-claw"
    }
  }
}
```

**Session persistence:**
```json
{
  "session": {
    "reset": {
      "mode": "idle",
      "idleMinutes": 10080
    }
  }
}
```

**Environment variables (in OpenClaw environment):**
```
LCM_FRESH_TAIL_COUNT=32
LCM_INCREMENTAL_MAX_DEPTH=-1
LCM_CONTEXT_THRESHOLD=0.75
LCM_PRUNE_HEARTBEAT_OK=true
```

### Phase 3: Telegram Import

**Script:** `scripts/telegram-import.py`  
**Dependencies:** Python 3.8+, stdlib only (zero external dependencies)  
**Input:** Telegram Desktop JSON export (`result.json`)

**Key flags:**
```
--user-name "Name"     Human sender name in the export (required)
--until YYYY-MM-DD     Import only messages before this date (prevents DAG overlap)
--since YYYY-MM-DD     Import only messages after this date
--chunk-days N         Split import into N-day conversation chunks (default: 30)
--dry-run              Preview without writing to DB
--verbose              Show per-message progress
```

**Handoff convention:** Set `--until` to the day before lossless-claw was installed. This creates a clean boundary: historical import covers everything up to that date, live DAG covers everything after. No duplicates.

**Database target:** `/root/.openclaw/lcm.db` (same DB as lossless-claw — data is immediately searchable via existing lcm tools)

### Phase 4: QMD — Personal Knowledge Base

**Plugin:** `@openclaw/qmd`  
**Search modes:** BM25 (keyword) + vector (semantic)  
**Tool:** `qmd_search` (already available in agent tool set)

**Configuration in openclaw.json:**
```json
{
  "plugins": {
    "entries": {
      "qmd": {
        "enabled": true,
        "config": {
          "root": "/root/life"
        }
      }
    }
  }
}
```

**Recall priority order (full four-layer stack):**
1. lossless-claw DAG — conversation history (recent + backfilled)
2. QMD — personal knowledge base
3. Vault — operational reference (on-demand reads)
4. memory_search — MEMORY.md fallback

---

## 6. Success Metrics

| Metric | Before | Target | How measured |
|---|---|---|---|
| Injected tokens per message | ~11,964 | <2,100 | wc -c on workspace files / 3.8 |
| Total injected bytes | 45,903 | <8,192 | wc -c on workspace files |
| Context degradation on long sessions | Drops old messages silently | Zero loss | lossless-claw DAG |
| Time to first token | Baseline (not measured) | Noticeable improvement | Subjective + timing |
| Identity preservation | N/A | 100% | Manual review of SOUL.md / IDENTITY.md |
| Memory searchability | QMD over ~/life/ only | QMD + vault/ + LCM | Test queries post-migration |

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Vault migration loses context | Low | High | Nothing deleted, only moved; full backup exists |
| SOUL.md edit damages personality | Low | High | Manual surgical edit; preserve all identity markers |
| lossless-claw plugin breaks sessions | Low | Medium | Plugin can be disabled; falls back to default compaction |
| lossless-claw summarization costs | Low | Low | Summarization is infrequent (triggered at 75% context) |
| Pointer references break (wrong path) | Medium | Low | All vault paths verified after migration |
| Session reset wipes LCM database | Low | Medium | LCM_DATABASE_PATH persists at ~/.openclaw/lcm.db |

---

## 8. Implementation Order

**Phase 1: Vault Architecture**
1. **Measure baseline** ✅ (done — see Section 5)
2. **Create vault/ directory structure** ✅
3. **Migrate MEMORY.md** — largest file, highest impact, safest to start (pure migration, no identity risk)
4. **Migrate TOOLS.md** — second largest, purely operational content
5. **Edit AGENTS.md** — trim procedural verbosity, keep decision framework
6. **Edit SOUL.md** — most sensitive; audit every deletion
7. **Verify Phase 1** — measure new sizes, confirm under 8KB

**Phase 2: Lossless Context Management**
8. **Install lossless-claw** — `openclaw plugins install @martian-engineering/lossless-claw`
9. **Configure lossless-claw** — edit openclaw.json (freshTailCount, contextThreshold, incrementalMaxDepth)
10. **Configure session persistence** — set idleMinutes: 10080
11. **Restart and verify** — confirm plugin loads, lcm.db created

**Phase 3: Telegram Import**
12. **Export Telegram chat history** — Telegram Desktop → ⋮ → Export chat history → JSON
13. **Dry-run import** — preview with `--dry-run` flag, set `--until` to day before lossless-claw install
14. **Run import** — `python3 scripts/telegram-import.py result.json --user-name "Name" --until YYYY-MM-DD --chunk-days 30`
15. **Verify backfill** — ask agent to recall something from before lossless-claw was installed

**Phase 4: QMD**
16. **Set up knowledge base directory** — organize or locate existing notes (Obsidian, markdown, etc.)
17. **Install QMD** — `openclaw plugins install @openclaw/qmd`
18. **Configure QMD root** — set root path in openclaw.json
19. **Verify indexing** — test search via agent
20. **Update AGENTS.md** — add QMD to recall priority order
21. **Write key facts** — backfill any important knowledge that isn't in vault or conversation history



---

## 9. Deliverables

| Artifact | Description | Destination |
|---|---|---|
| `PRD.md` | This document | Repo root |
| `IMPLEMENTATION-GUIDE.md` | Step-by-step implementation guide (all 4 phases) | Repo root |
| `BEFORE-AFTER.md` | Side-by-side file comparisons with measurements | Repo root |
| `templates/SOUL-template.md` | Slim SOUL.md template (example, not your values) | /templates |
| `templates/AGENTS-template.md` | Slim AGENTS.md template | /templates |
| `templates/MEMORY-template.md` | Pointer-index MEMORY.md template | /templates |
| `templates/TOOLS-template.md` | Quick-reference TOOLS.md template | /templates |
| `templates/vault/` | Example vault/ structure with placeholder files | /templates/vault |
| `scripts/audit.sh` | Measures current workspace file sizes and token estimates | /scripts |
| `scripts/telegram-import.py` | Backfills Telegram chat history into lossless-claw SQLite | /scripts |
| `docs/telegram-import.md` | Full documentation for telegram-import.py (flags, FAQs, examples) | /docs |


---

## 10. Why This Matters Beyond Frank

Every OpenClaw user with a long-running agent faces this exact problem. The longer an agent runs, the more its workspace files bloat, and the more painful it becomes to optimize. The existing one-shot guides are written for fresh setups.

This is the guide for agents that have already been somewhere.

The vault architecture and lossless-claw combination solve different parts of the same problem. Slim files make every message cheaper and faster. LCM makes long sessions lossless. Together they create an agent that is simultaneously leaner, faster, cheaper to run, and more capable of recalling deep history than the default setup.

The key insight: **your agent's identity is not in the file size. It's in the content. You can have a 1KB SOUL.md that is fully, authentically you — if the right things are in it.**
