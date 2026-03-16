#!/usr/bin/env python3
"""
telegram-import.py — Import a Telegram chat export into a lossless-claw SQLite database.

Telegram exports chat history via: Settings → Advanced → Export Telegram Data → JSON format.
The exported file is typically named result.json.

Usage examples:
    # Basic import
    python3 telegram-import.py result.json

    # Specify who is the "user" side of the conversation
    python3 telegram-import.py result.json --user-name "Robbie"

    # Split into 30-day chunks (good for long chats)
    python3 telegram-import.py result.json --chunk-days 30

    # Preview without writing
    python3 telegram-import.py result.json --dry-run

    # Filter by date range
    python3 telegram-import.py result.json --since 2026-01-01 --until 2026-03-01

    # Custom DB path
    python3 telegram-import.py result.json --db /path/to/lcm.db

    # Skip media messages entirely
    python3 telegram-import.py result.json --skip-media

    # Verbose: print each message as it's processed
    python3 telegram-import.py result.json --verbose
"""

import argparse
import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

# Media type fields present in Telegram export messages
_MEDIA_FIELD_MAP = {
    "photo":         "[photo]",
    "sticker":       "[sticker]",
    "animation":     "[animation]",
    "video_file":    "[video]",
    "audio_file":    "[audio]",
    "voice_message": "[voice message]",
    "video_message": "[video message]",
    "document":      "[file]",
    "location":      "[location]",
    "poll":          "[poll]",
    "contact":       "[contact]",
}

_MEDIA_TYPE_MAP = {
    "photo":         "[photo]",
    "sticker":       "[sticker]",
    "animation":     "[animation]",
    "video_file":    "[video]",
    "audio_file":    "[audio]",
    "voice_message": "[voice message]",
    "video_message": "[video message]",
    "document":      "[file]",
}


def flatten_text(raw) -> str:
    """
    Flatten Telegram's text field into a plain string.

    The field may be:
      - A plain string: "hello"
      - A list of strings and/or entity dicts: ["Check out ", {"type": "link", "text": "x.com"}]
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "".join(parts)
    return ""


def extract_content(msg: dict, skip_media: bool) -> tuple[str | None, bool]:
    """
    Return (content_string, is_media).

    Returns (None, False) if the message should be skipped entirely.
    Returns ("[photo]" etc., True) for media unless skip_media=True.
    Returns (text, False) for regular text messages.
    """
    # Check for media via "media_type" field
    media_type = msg.get("media_type")
    if media_type:
        if skip_media:
            return None, True
        label = _MEDIA_TYPE_MAP.get(media_type, f"[{media_type}]")
        text = flatten_text(msg.get("text", ""))
        return (f"{label} {text}".strip() if text else label), True

    # Check for media via specific fields (photo, sticker, etc.)
    for field, label in _MEDIA_FIELD_MAP.items():
        if field in msg:
            if skip_media:
                return None, True
            text = flatten_text(msg.get("text", ""))
            return (f"{label} {text}".strip() if text else label), True

    # Plain text message
    text = flatten_text(msg.get("text", ""))
    return text, False


# ---------------------------------------------------------------------------
# Telegram JSON parsing
# ---------------------------------------------------------------------------

def parse_export(path: str) -> dict:
    """Load and parse the Telegram export JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        sys.exit(f"Error: File not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"Error: Malformed JSON in {path}: {e}")
    return data


def detect_user_name(messages: list[dict]) -> str | None:
    """Return the from field of the first message with a from field."""
    for msg in messages:
        if msg.get("type") == "message" and msg.get("from"):
            return msg["from"]
    return None


def parse_date(msg: dict) -> date | None:
    """Parse the date field of a message into a date object."""
    raw = msg.get("date", "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_messages(messages: list[dict], chunk_days: int) -> list[list[dict]]:
    """
    Split messages into chunks of up to chunk_days days each.
    Returns a list of message-lists.
    """
    if chunk_days <= 0:
        return [messages]

    if not messages:
        return []

    chunks = []
    current_chunk = []
    chunk_start: date | None = None

    for msg in messages:
        msg_date = parse_date(msg)
        if msg_date is None:
            # No date info — attach to current chunk
            current_chunk.append(msg)
            continue

        if chunk_start is None:
            chunk_start = msg_date

        if (msg_date - chunk_start).days >= chunk_days:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = [msg]
            chunk_start = msg_date
        else:
            current_chunk.append(msg)

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def open_db(db_path: str) -> sqlite3.Connection:
    """Open the SQLite DB with retry logic for locked databases."""
    for attempt in range(3):
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 2:
                print(f"Warning: DB locked, retrying ({attempt + 1}/3)…")
                time.sleep(1)
            else:
                sys.exit(f"Error: Cannot open database: {e}")
    sys.exit("Error: Database is locked after 3 retries.")


def check_existing_imports(conn: sqlite3.Connection) -> int:
    """Return count of existing Telegram import conversations."""
    row = conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE title LIKE 'Telegram:%'"
    ).fetchone()
    return row[0] if row else 0


def insert_conversation(conn: sqlite3.Connection, session_id: str, title: str) -> int:
    """Insert a new conversation row and return its conversation_id."""
    cur = conn.execute(
        """
        INSERT INTO conversations (session_id, title, created_at, updated_at)
        VALUES (?, ?, datetime('now'), datetime('now'))
        """,
        (session_id, title),
    )
    return cur.lastrowid


def insert_message(
    conn: sqlite3.Connection,
    conversation_id: int,
    seq: int,
    role: str,
    content: str,
) -> int:
    """Insert a message row and return its message_id."""
    token_count = max(1, len(content) // 4)
    cur = conn.execute(
        """
        INSERT INTO messages (conversation_id, seq, role, content, token_count, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (conversation_id, seq, role, content, token_count),
    )
    return cur.lastrowid


def insert_message_part(
    conn: sqlite3.Connection,
    message_id: int,
    session_id: str,
    content: str,
) -> None:
    """Insert a single text part for the given message."""
    conn.execute(
        """
        INSERT INTO message_parts
          (part_id, message_id, session_id, part_type, ordinal, text_content, is_ignored, is_synthetic)
        VALUES (?, ?, ?, 'text', 0, ?, 0, 0)
        """,
        (str(uuid.uuid4()), message_id, session_id, content),
    )


def insert_fts(conn: sqlite3.Connection, message_id: int, content: str) -> None:
    """Populate the full-text search index for a message."""
    conn.execute(
        "INSERT INTO messages_fts(rowid, content) VALUES (?, ?)",
        (message_id, content),
    )


# ---------------------------------------------------------------------------
# Core import logic
# ---------------------------------------------------------------------------

def import_chunk(
    conn: sqlite3.Connection,
    chunk: list[dict],
    title: str,
    user_name: str,
    skip_media: bool,
    verbose: bool,
    dry_run: bool,
) -> dict:
    """
    Process one chunk of messages and (if not dry_run) write to DB.

    Returns a stats dict: {imported, skipped_media, skipped_service, user_count, assistant_count}.
    """
    stats = {
        "imported": 0,
        "skipped_media": 0,
        "skipped_service": 0,
        "user_count": 0,
        "assistant_count": 0,
    }

    session_id = str(uuid.uuid4())

    if not dry_run:
        conversation_id = insert_conversation(conn, session_id, title)
    else:
        conversation_id = -1  # unused in dry run

    seq = 0

    for msg in chunk:
        # Skip non-message types (service messages, phone_call, etc.)
        if msg.get("type") != "message":
            stats["skipped_service"] += 1
            continue

        content, is_media = extract_content(msg, skip_media)

        if content is None:
            # skip_media=True and this was a media message
            stats["skipped_media"] += 1
            continue

        if is_media:
            stats["skipped_media"] += 1  # counted even when included (for summary)
            # We still import the placeholder — fall through

        sender = msg.get("from", "")
        role = "user" if sender == user_name else "assistant"

        if role == "user":
            stats["user_count"] += 1
        else:
            stats["assistant_count"] += 1

        if verbose:
            ts = msg.get("date", "")[:19]
            print(f"  [{ts}] {role:9s} ({sender}): {content[:80]}")

        if not dry_run:
            message_id = insert_message(conn, conversation_id, seq, role, content)
            insert_message_part(conn, message_id, session_id, content)
            insert_fts(conn, message_id, content)

        stats["imported"] += 1
        seq += 1

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import a Telegram chat export into a lossless-claw SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Path to Telegram result.json export file")
    parser.add_argument(
        "--db",
        default=str(Path("~/.openclaw/lcm.db").expanduser()),
        help="Path to lcm.db (default: ~/.openclaw/lcm.db)",
    )
    parser.add_argument(
        "--user-name",
        metavar="NAME",
        help="Sender name that maps to role='user' (default: auto-detect first sender)",
    )
    parser.add_argument(
        "--title",
        metavar="TEXT",
        help="Conversation title in DB (default: 'Telegram: <chat name>')",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=0,
        metavar="N",
        help="Split into N-day chunks (default: 0 = one conversation per import)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing to DB",
    )
    parser.add_argument(
        "--skip-media",
        action="store_true",
        help="Omit media messages entirely (default: include as [photo] etc.)",
    )
    parser.add_argument(
        "--since",
        metavar="DATE",
        help="Only import messages on/after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until",
        metavar="DATE",
        help="Only import messages on/before this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each message as it's imported",
    )
    args = parser.parse_args()

    # --- Parse since/until dates ---
    since_date = until_date = None
    if args.since:
        try:
            since_date = date.fromisoformat(args.since)
        except ValueError:
            sys.exit(f"Error: --since must be YYYY-MM-DD, got: {args.since}")
    if args.until:
        try:
            until_date = date.fromisoformat(args.until)
        except ValueError:
            sys.exit(f"Error: --until must be YYYY-MM-DD, got: {args.until}")

    # --- Load export ---
    export = parse_export(args.input)
    chat_name = export.get("name", "Unknown Chat")
    all_messages = export.get("messages", [])

    # --- Auto-detect user name ---
    user_name = args.user_name or detect_user_name(all_messages)
    if not user_name:
        sys.exit("Error: Could not detect sender name. Use --user-name to specify.")

    # --- Filter by date ---
    if since_date or until_date:
        filtered = []
        for msg in all_messages:
            d = parse_date(msg)
            if d is None:
                filtered.append(msg)  # no date info — include
                continue
            if since_date and d < since_date:
                continue
            if until_date and d > until_date:
                continue
            filtered.append(msg)
        all_messages = filtered

    # --- Chunk messages ---
    chunks = chunk_messages(all_messages, args.chunk_days)

    # --- Title template ---
    base_title = args.title or f"Telegram: {chat_name}"

    # --- DB path warning ---
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Warning: DB file not found at {db_path}")
        if args.dry_run:
            print("         (dry run — no DB access needed)")
        else:
            sys.exit("Error: DB file not found. Check --db path.")

    if args.dry_run:
        print("⚠️  DRY RUN — no changes will be written to the database\n")

    # --- Open DB (skip for dry run if file missing) ---
    conn = None
    if not args.dry_run:
        conn = open_db(str(db_path))

        # Safety: warn if previous Telegram imports exist
        existing = check_existing_imports(conn)
        if existing > 0:
            print(
                f"Warning: Found {existing} existing Telegram import conversation(s) in DB. "
                "Proceeding will add more."
            )

    # --- Run import ---
    totals = {
        "conversations": 0,
        "imported": 0,
        "skipped_media": 0,
        "skipped_service": 0,
        "user_count": 0,
        "assistant_count": 0,
    }

    all_dates: list[date] = []

    try:
        if conn:
            conn.execute("BEGIN")

        for i, chunk in enumerate(chunks):
            if not chunk:
                continue

            # Build title for this chunk
            if len(chunks) > 1:
                chunk_title = f"{base_title} (part {i + 1}/{len(chunks)})"
            else:
                chunk_title = base_title

            # Collect dates for summary
            for msg in chunk:
                d = parse_date(msg)
                if d:
                    all_dates.append(d)

            if args.verbose:
                print(f"\n--- {chunk_title} ---")

            stats = import_chunk(
                conn=conn,
                chunk=chunk,
                title=chunk_title,
                user_name=user_name,
                skip_media=args.skip_media,
                verbose=args.verbose,
                dry_run=args.dry_run,
            )

            totals["conversations"] += 1
            totals["imported"] += stats["imported"]
            totals["skipped_media"] += stats["skipped_media"]
            totals["skipped_service"] += stats["skipped_service"]
            totals["user_count"] += stats["user_count"]
            totals["assistant_count"] += stats["assistant_count"]

        if conn:
            conn.commit()

    except Exception as e:
        if conn:
            conn.rollback()
        sys.exit(f"Error: Import failed and was rolled back: {e}")
    finally:
        if conn:
            conn.close()

    # --- Summary ---
    date_range = "n/a"
    if all_dates:
        date_range = f"{min(all_dates)} → {max(all_dates)}"

    skipped_note = ""
    if args.skip_media:
        skipped_note = " (omitted)"
    else:
        skipped_note = " (included as placeholders)"

    print()
    if args.dry_run:
        print("⚠️  DRY RUN complete — nothing was written\n")
    else:
        print("✅ Import complete")
    print(f"   Conversation(s) created: {totals['conversations']}")
    print(f"   Messages imported:       {totals['imported']} (user: {totals['user_count']}, assistant: {totals['assistant_count']})")
    print(f"   Skipped (media):         {totals['skipped_media']}{skipped_note}")
    print(f"   Skipped (service msgs):  {totals['skipped_service']}")
    print(f"   Date range:              {date_range}")
    print(f"   DB:                      {db_path}")
    print(f"   User name mapped to 'user' role: {user_name}")


if __name__ == "__main__":
    main()
