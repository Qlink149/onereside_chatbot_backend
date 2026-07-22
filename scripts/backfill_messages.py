"""
One-off script: copy every user's embedded chat_history entries into the
new `messages` collection.

Run this BEFORE deploying the capped chat_history change — after that deploy
the embedded array is trimmed to the last CHAT_HISTORY_MAX entries on each
new message, so older entries would be lost if not preserved here first.

Idempotent: users already backfilled (messages_backfilled flag) are skipped,
and a re-run after a crash first deletes that user's backfilled docs before
re-inserting.

Run from the repo root:
    python -m scripts.backfill_messages
Add --dry-run to preview counts without writing:
    python -m scripts.backfill_messages --dry-run
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onereside_chatbot.database.collections import idac, messages


def main(dry_run: bool = False) -> None:
    users = idac.find(
        {"messages_backfilled": {"$ne": True}},
        {"phone_number": 1, "chat_history": 1},
    )

    total_users = 0
    total_messages = 0

    for user in users:
        phone_number = user.get("phone_number")
        chat_history = user.get("chat_history") or []
        if not phone_number:
            continue

        docs = [
            {
                "phone_number": phone_number,
                "turn_id": None,
                "role": entry.get("role", "unknown"),
                "type": "text",
                "content": entry.get("content", ""),
                "raw": None,
                "context": None,
                "timestamp": entry.get("timestamp") or 0,
                "backfilled": True,
            }
            for entry in chat_history
            if isinstance(entry, dict)
        ]

        total_users += 1
        total_messages += len(docs)

        if dry_run:
            print(f"[dry-run] {phone_number}: {len(docs)} entries")
            continue

        # Crash-safe: wipe any partial backfill for this user, then insert + flag
        messages.delete_many({"phone_number": phone_number, "backfilled": True})
        if docs:
            messages.insert_many(docs)
        idac.update_one(
            {"phone_number": phone_number},
            {"$set": {"messages_backfilled": True}},
        )
        print(f"{phone_number}: backfilled {len(docs)} entries")

    action = "Would backfill" if dry_run else "Backfilled"
    print(f"\n{action} {total_messages} messages across {total_users} users.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
