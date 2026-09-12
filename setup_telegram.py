"""Interactive Telegram setup. Run once.

Validates your bot token, auto-detects your chat ID (no @userinfobot needed),
writes both into .env, and sends a test message to prove it works.

    python setup_telegram.py
"""
import re
import sys
import time
from pathlib import Path

import requests

ENV_FILE = Path(__file__).parent / ".env"
API = "https://api.telegram.org/bot{token}/{method}"


def api(token: str, method: str, **params):
    resp = requests.get(API.format(token=token, method=method), params=params, timeout=30)
    return resp.json()


def validate_token(token: str) -> str | None:
    """Returns the bot's @username if the token is good, else None."""
    try:
        data = api(token, "getMe")
    except requests.RequestException as exc:
        print(f"   Could not reach Telegram: {exc}")
        return None
    if not data.get("ok"):
        print(f"   Telegram rejected that token: {data.get('description', 'unknown error')}")
        return None
    return data["result"]["username"]


def find_chat_id(token: str, attempts: int = 30) -> str | None:
    """Poll getUpdates until the user messages the bot."""
    # Clear any backlog so we only pick up a fresh message.
    seen = api(token, "getUpdates")
    offset = 0
    if seen.get("ok") and seen.get("result"):
        offset = seen["result"][-1]["update_id"] + 1

    for i in range(attempts):
        data = api(token, "getUpdates", offset=offset, timeout=2)
        for update in data.get("result", []):
            msg = update.get("message") or update.get("edited_message")
            if msg and msg.get("chat"):
                chat = msg["chat"]
                name = chat.get("first_name") or chat.get("title") or "you"
                print(f"\n   Got a message from {name}!")
                return str(chat["id"])
        print(f"   ...waiting ({i + 1}/{attempts})", end="\r", flush=True)
        time.sleep(2)
    return None


def write_env(token: str, chat_id: str) -> None:
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    for key, value in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)):
        if re.search(rf"^{key}=.*$", text, re.M):
            text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
        else:
            text += f"\n{key}={value}\n"
    ENV_FILE.write_text(text, encoding="utf-8")


def main() -> int:
    print("=" * 64)
    print(" TELEGRAM SETUP")
    print("=" * 64)
    print()
    print(" First, create your bot (skip if you already have a token):")
    print("   1. Open Telegram, search for  @BotFather")
    print("   2. Send:  /newbot")
    print("   3. Give it any name, then any username ending in 'bot'")
    print("   4. BotFather replies with a token like 8123456789:AAH...")
    print()

    try:
        token = input(" Paste your bot token here: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n Cancelled.")
        return 1

    if not token:
        print(" No token entered. Nothing changed.")
        return 1

    print("\n Checking token...")
    username = validate_token(token)
    if not username:
        print("\n That token didn't work. Double-check you copied the whole thing.")
        return 1
    print(f"   Token is valid - your bot is @{username}")

    print()
    print(" Now open this chat and send it any message (e.g. 'hi'):")
    print(f"     https://t.me/{username}")
    print()
    print(" (You must press START in that chat - Telegram blocks bots from")
    print("  messaging you until you do.)")
    print()

    chat_id = find_chat_id(token)
    if not chat_id:
        print("\n Never saw a message. Make sure you pressed START and sent something,")
        print(" then run this script again.")
        return 1

    print(f"   Your chat ID is {chat_id}")

    write_env(token, chat_id)
    print(f"\n Saved both values into {ENV_FILE.name}")

    print("\n Sending a test message...")
    result = requests.post(
        API.format(token=token, method="sendMessage"),
        json={"chat_id": chat_id,
              "text": "\u2705 <b>FirstCry bot connected!</b>\n\nYou'll get Hot Wheels alerts here.",
              "parse_mode": "HTML"},
        timeout=30,
    ).json()

    if result.get("ok"):
        print(" Sent! Check your Telegram - you should see it now.")
        print("\n Setup complete. Next:  python bot1_new_arrivals.py")
        return 0

    print(f" Telegram refused: {result.get('description')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
