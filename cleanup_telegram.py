"""Delete the bot's own recent messages from Telegram.

Useful after a test run, or when an account is removed and you don't want
its old alerts sitting in the chat.

Telegram gives no way to list what a bot has sent, so this works backwards:
it posts a probe message to learn the current message id, then walks down
from there deleting. A bot can only ever delete its OWN messages (unless it
is a group admin), so anything you wrote is left alone.

Telegram also refuses to delete messages older than 48 hours.

    python cleanup_telegram.py            # last 50 messages
    python cleanup_telegram.py --count 200
"""
import argparse
import sys
import time

import requests

import config

API = "https://api.telegram.org/bot{token}/{method}"


def api(method: str, **params) -> dict:
    try:
        return requests.post(API.format(token=config.TELEGRAM_BOT_TOKEN,
                                        method=method),
                             json=params, timeout=20).json()
    except requests.RequestException as exc:
        return {"ok": False, "description": str(exc)}


def clean_chat(chat_id: str, count: int) -> tuple[int, int]:
    """Returns (deleted, checked)."""
    probe = api("sendMessage", chat_id=chat_id, text="\U0001f9f9 cleaning up…")
    if not probe.get("ok"):
        print(f"   cannot post to {chat_id}: {probe.get('description')}")
        return 0, 0

    newest = probe["result"]["message_id"]
    deleted = 0
    checked = 0

    # Walk backwards from the probe, deleting whatever belongs to the bot.
    for mid in range(newest, max(0, newest - count), -1):
        checked += 1
        if api("deleteMessage", chat_id=chat_id, message_id=mid).get("ok"):
            deleted += 1
        # Telegram rate-limits deletes fairly aggressively.
        time.sleep(0.06)

    return deleted, checked


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Delete the bot's own recent Telegram messages")
    ap.add_argument("--count", type=int, default=50,
                    help="how many message ids to walk back through "
                         "(default 50)")
    args = ap.parse_args()

    if not config.telegram_ready():
        print("Telegram isn't configured - nothing to clean.")
        return 1

    print("=" * 58)
    print(" TELEGRAM CLEANUP")
    print("=" * 58)
    print(f" Walking back {args.count} messages in "
          f"{len(config.TELEGRAM_CHAT_IDS)} chat(s).")
    print(" Only the bot's own messages can be removed; yours are safe.")
    print(" Telegram refuses anything older than 48 hours.\n")

    total_deleted = 0
    for chat_id in config.TELEGRAM_CHAT_IDS:
        print(f"  chat {chat_id} ...", end=" ", flush=True)
        deleted, checked = clean_chat(chat_id, args.count)
        total_deleted += deleted
        print(f"deleted {deleted} of {checked} checked")

    print(f"\n Removed {total_deleted} message(s).")
    if total_deleted == 0:
        print(" Nothing deleted - they may be over 48 hours old, in which")
        print(" case Telegram only allows removing them by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
