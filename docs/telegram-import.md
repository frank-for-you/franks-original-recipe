# Telegram History Import

`scripts/telegram-import.py` — Backfill your entire Telegram chat history into lossless-claw's SQLite database, giving your agent full searchable recall from day one.

---

## Why This Exists

lossless-claw starts capturing context from the moment it's installed. Everything before that is gone. If you've been talking to your agent via Telegram for weeks or months, you just lost all of that history.

This script fixes it. Export your chat, run the import, done. Your agent can now search and recall any conversation you've ever had.

---

## Step 1 — Export Your Telegram Chat

1. Open Telegram Desktop (mobile doesn't support exports)
2. Open the chat with your agent
3. Click the **⋮** menu (top right) → **Export chat history**
4. Set format to **JSON**
5. Uncheck photos/videos/etc. if you want a smaller export (the script handles missing media gracefully)
6. Click **Export**

Telegram saves the export as a folder containing `result.json` (plus any media files if you included them).

---

## Step 2 — Run the Import

**Basic usage:**
```bash
python3 telegram-import.py /path/to/result.json --user-name "YourName"
```

**Recommended for most users** (stops before lossless-claw came online, avoids duplicate messages):
```bash
python3 telegram-import.py result.json \
  --user-name "Robbie" \
  --until 2026-03-15 \
  --chunk-days 30
```

**Always dry-run first:**
```bash
python3 telegram-import.py result.json --user-name "Robbie" --until 2026-03-15 --dry-run
```

---

## All Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--db PATH` | `~/.openclaw/lcm.db` | Path to your lossless-claw database |
| `--user-name NAME` | Auto-detect | Sender name that maps to `role='user'`. Set this explicitly to avoid misdetection. |
| `--title TEXT` | `Telegram: <chat name>` | Custom title for the imported conversation(s) in the DB |
| `--chunk-days N` | `0` (no chunking) | Split into N-day batches. Recommended: `30` for chats longer than a month |
| `--dry-run` | off | Preview what would be imported without touching the DB |
| `--skip-media` | off | Omit photo/sticker/voice messages entirely. Default: include as `[photo]` placeholders |
| `--since YYYY-MM-DD` | none | Only import messages on or after this date |
| `--until YYYY-MM-DD` | none | Only import messages on or before this date |
| `--verbose` | off | Print each message as it's processed |

---

## Handling the Overlap Problem

If lossless-claw has been running for any amount of time, your DB already has some messages — and your Telegram export also has those same messages. Running the import without filtering would duplicate tonight's content.

**The clean fix:** use `--until` set to the day before lossless-claw came online.

```bash
# lossless-claw installed March 16 → import everything through March 15
python3 telegram-import.py result.json --user-name "Robbie" --until 2026-03-15
```

This gives you:
- `result.json` import → March 7–15 (historical)
- lossless-claw DB → March 16+ (live)

Zero overlap.

---

## Chunking Long Chats

For chats longer than a month, use `--chunk-days 30`. This splits the import into 30-day conversations instead of one giant one.

Why it matters: lossless-claw's summarization engine works per-conversation. One massive conversation (1000+ messages) is harder to summarize efficiently than several 200-message chunks covering logical time windows.

```bash
python3 telegram-import.py result.json --user-name "Robbie" --chunk-days 30
```

Output will show `part 1/4`, `part 2/4`, etc. in the conversation titles.

---

## Verifying the Import

After running, confirm everything landed correctly:

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/.openclaw/lcm.db')
for row in conn.execute('SELECT conversation_id, title, created_at FROM conversations'):
    print(row[0], row[1], row[2])
# Test FTS search
results = conn.execute(\"SELECT COUNT(*) FROM messages_fts WHERE content MATCH 'stripe'\").fetchone()
print(f'FTS hits for stripe: {results[0]}')
conn.close()
"
```

---

## Safety Guarantees

- **Never modifies the active conversation.** Import always creates new conversations, never touches conversation_id 1 or any existing live session.
- **Single transaction.** If anything fails mid-import, the entire batch is rolled back. You won't end up with partial data.
- **Duplicate import warning.** If you've already run an import, the script warns you before proceeding.
- **DB not found.** If the DB path doesn't exist, the script exits cleanly rather than creating a new empty database in the wrong location.

---

## FAQs

**Q: Do I need to include media files in the export?**
No. The script handles missing media gracefully — media messages without accompanying files are just imported as `[photo]`, `[sticker]`, etc. Use `--skip-media` if you don't want these placeholders at all.

**Q: What about service messages (someone joined, pinned a message, etc.)?**
Skipped silently. They're counted in the "skipped (service msgs)" total but never written to the DB.

**Q: What if I run it twice by accident?**
You'll get duplicate conversations. The script warns you if it detects a prior Telegram import. If it happens, you can delete the duplicate conversation manually:
```sql
DELETE FROM message_parts WHERE message_id IN (SELECT message_id FROM messages WHERE conversation_id = X);
DELETE FROM messages_fts WHERE rowid IN (SELECT message_id FROM messages WHERE conversation_id = X);
DELETE FROM messages WHERE conversation_id = X;
DELETE FROM conversations WHERE conversation_id = X;
```
Replace `X` with the duplicate `conversation_id`.

**Q: How does it know which sender is "user" vs "assistant"?**
By name. Pass `--user-name "Robbie"` and every message from "Robbie" gets `role='user'`, everything else gets `role='assistant'`. If you skip the flag, it auto-detects from the first sender in the export — which is usually right for personal chats but not always.

**Q: Will this affect my agent's current context window?**
No. The imported conversations are separate from the active session. Your agent accesses them via `lcm_grep` / `lcm_expand_query` using `allConversations: true`. They don't appear in the live context unless explicitly searched.

**Q: Does it require any dependencies beyond Python stdlib?**
No. Pure Python 3.8+, only stdlib modules (`sqlite3`, `json`, `argparse`, `uuid`, `datetime`, `pathlib`).

**Q: What's the token estimation method?**
`max(1, len(text) // 4)` — a simple heuristic. No tiktoken or external tokenizer required. Accurate enough for lossless-claw's purposes.

---

## Example Output

```
✅ Import complete
   Conversation(s) created: 3
   Messages imported:       1773 (user: 437, assistant: 1336)
   Skipped (media):         26 (included as placeholders)
   Skipped (service msgs):  0
   Date range:              2026-03-07 → 2026-03-15
   DB:                      /root/.openclaw/lcm.db
   User name mapped to 'user' role: Robbie
```
