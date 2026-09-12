"""Find the chat ID of a group (or anyone) so the bots can post there.

Groups don't advertise their ID anywhere in the Telegram UI. The way to get
it is to make the bot see a message in that group, then read it back from
Telegram's API. This script does the reading part.

    python find_chat_ids.py

It listens for ~60 seconds. Send "/start" in the group while it's running.
"""
import sys
import time

import requests

import config

API = "https://api.telegram.org/bot{token}/{method}"
LISTEN_SECONDS = 60

KIND = {"private": "direct message",
        "group": "group",
        "supergroup": "group",
        "channel": "channel"}


def api(method: str, **params):
    resp = requests.get(API.format(token=config.TELEGRAM_BOT_TOKEN, method=method),
                        params=params, timeout=30)
    return resp.json()


def main() -> int:
    if not config.TELEGRAM_BOT_TOKEN:
        print(" No TELEGRAM_BOT_TOKEN in .env - run setup_telegram.py first.")
        return 1

    me = api("getMe")
    if not me.get("ok"):
        print(f" Telegram rejected the token: {me.get('description')}")
        return 1
    username = me["result"]["username"]

    print("=" * 66)
    print(" FIND CHAT IDs")
    print("=" * 66)
    print()
    print(f" Your bot is @{username}")
    print()
    print(" To add it to a group:")
    print()
    print("   1. Open the group in Telegram")
    print("   2. Tap the group name -> Add Members")
    print(f"   3. Search for  {username}  and add it")
    print("   4. In the group, send:   /start")
    print()
    print(" Bots can't read normal group chatter by default, but they ALWAYS")
    print(" see messages beginning with '/', which is why /start works.")
    print()
    print(f" Listening for {LISTEN_SECONDS} seconds - send /start now...")
    print("=" * 66)

    # Skip anything already queued so we only report fresh chats.
    seen_updates = api("getUpdates")
    offset = 0
    if seen_updates.get("ok") and seen_updates.get("result"):
        offset = seen_updates["result"][-1]["update_id"] + 1

    found: dict[str, dict] = {}
    deadline = time.time() + LISTEN_SECONDS

    while time.time() < deadline:
        data = api("getUpdates", offset=offset, timeout=5)
        for update in data.get("result", []):
            offset = update["update_id"] + 1
            msg = (update.get("message") or update.get("edited_message")
                   or update.get("channel_post") or update.get("my_chat_member"))
            if not msg or not msg.get("chat"):
                continue
            chat = msg["chat"]
            cid = str(chat["id"])
            if cid in found:
                continue
            name = chat.get("title") or " ".join(
                filter(None, [chat.get("first_name"), chat.get("last_name")])) or "?"
            found[cid] = {"name": name, "type": chat.get("type", "?")}
            print(f"\n   FOUND  {KIND.get(chat.get('type'), chat.get('type')):<15} "
                  f"{name}\n          chat ID: {cid}")

        remaining = int(deadline - time.time())
        if remaining > 0:
            print(f"   ...listening ({remaining}s left)   ", end="\r", flush=True)
        time.sleep(1)

    print(" " * 50, end="\r")

    if not found:
        print("\n Nothing heard.")
        print(" Make sure the bot is IN the group, and that you sent /start there.")
        print(" If the group has 'Restrict Saving Content' or admin-only posting,")
        print(" check the bot is allowed to read messages.")
        return 1

    current = config.TELEGRAM_CHAT_IDS
    combined = list(dict.fromkeys(current + list(found)))

    print("\n" + "=" * 66)
    print(" RESULTS")
    print("=" * 66)
    for cid, info in found.items():
        print(f"   {info['name']:<28} {cid}")
    print()
    print(" Currently in .env :", ", ".join(current) or "(none)")
    print(" All together      :", ",".join(combined))
    print()
    print(" To send alerts to all of them, set this line in .env:")
    print(f"\n   TELEGRAM_CHAT_ID={','.join(combined)}\n")
    print(" (Or use just the group ID if you only want alerts there.)")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
