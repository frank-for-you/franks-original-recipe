# Ambient Retrieval Plugin

**RFC-03 implementation** — automatically surfaces relevant context from your knowledge base before each agent turn, without you having to decide to search.

---

## What it does

On every message you send, this plugin runs a QMD semantic search against your `~/life/` knowledge base, then injects the top matches into the system prompt before the agent sees your message.

The agent gets relevant context pre-loaded — no manual `memory_search` or `qmd_search` call needed.

---

## How it works

This plugin registers as an OpenClaw context engine called `ambient-retrieval`. It wraps the `lossless-claw` context engine:

1. Delegates all compaction, ingestion, and bootstrap to lossless-claw unchanged
2. Adds one step in `assemble()` (which runs before every turn): calls `qmd query` on the last user message
3. Injects results as `systemPromptAddition` — merged with lossless-claw's existing summaries

lossless-claw's tools (`lcm_grep`, `lcm_expand`, etc.) still work exactly as before.

**Fail-safe**: if QMD errors, returns nothing, or times out, the plugin returns lossless-claw's result unchanged. A broken QMD search never blocks a turn.

---

## Requirements

- lossless-claw must already be installed (this plugin wraps it)
- QMD must be installed and the `qmd` binary must be at `/usr/local/bin/qmd`
- A configured `~/life/` knowledge base indexed by QMD

---

## Installation

### 1. Copy plugin files

```bash
cp -r plugins/ambient-retrieval ~/.openclaw/extensions/
```

### 2. Update openclaw.json

Add to your `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "allow": ["lossless-claw", "qmd-search", "ambient-retrieval"],
    "entries": {
      "ambient-retrieval": { "enabled": true }
    },
    "installs": {
      "ambient-retrieval": {
        "source": "path",
        "installPath": "~/.openclaw/extensions/ambient-retrieval"
      }
    },
    "slots": {
      "contextEngine": "ambient-retrieval"
    }
  }
}
```

**Important:** Change `contextEngine` from `"lossless-claw"` to `"ambient-retrieval"`. lossless-claw will still handle all compaction — the slot change just means ambient-retrieval wraps it.

### 3. Reload the gateway

```bash
kill -HUP 1
```

(Or restart your OpenClaw container.)

### 4. Verify

Check your OpenClaw logs for:
```
[ambient-retrieval] Plugin loaded
[ambient-retrieval] lossless-claw engine acquired
```

---

## Configuration

No required config — works with defaults. Optional tuning in `openclaw.json`:

```json
"ambient-retrieval": {
  "enabled": true,
  "config": {
    "minQueryLength": 8,
    "maxResults": 3,
    "scoreThreshold": 0.0
  }
}
```

---

## Notes

- Adds ~200–500ms latency per turn (QMD search)
- Only searches against your QMD knowledge base (`~/life/`), not the LCM conversation history (lossless-claw handles that separately)
- Results are injected as system prompt context, not as a visible message
- Short messages (<8 chars) and system commands skip the search automatically
