"""Listen for Telegram commands, so the bots can be driven from your phone.

The point of this is session refresh. FirstCry's login runs reCAPTCHA, so a
human has to do the login itself - but nothing says the new cookies have to
reach the server over SSH. Paste them into Telegram and the bot updates
itself, from any machine with a browser.

Commands:
    /status     what is deliverable right now
    /cart       everything in the cart, deliverable or not
    /health     how old each login is
    /session    refresh a login - see below
    /pause      stop watching (bots keep running, just quiet)
    /resume     start watching again
    /help       this list

Refreshing a login:
    1. Log in to FirstCry in any browser
    2. Open https://checkout.firstcry.com/pay
    3. F12 -> Network -> F5 -> right-click first row -> Copy as cURL
    4. Send Telegram:   /session <paste>
       or for a named account:   /session SAI <paste>

SECURITY: commands are only accepted in a PRIVATE chat with the bot, never
in a group. A session cURL pasted into a group would hand your FirstCry
login to everyone in it.
"""
import json
import threading
import time
from datetime import datetime

import requests

import config
import firstcry_account as fa
import import_cookies
import notifier
import session_health

API = "https://api.telegram.org/bot{token}/{method}"

# Set when /pause is used; the watcher threads check it each cycle.
paused = threading.Event()

_OFFSET_FILE = config.STATE_DIR / "telegram_offset.json"


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] [TG] {msg}", flush=True)


def _api(method: str, **params) -> dict:
    try:
        return requests.post(API.format(token=config.TELEGRAM_BOT_TOKEN,
                                        method=method),
                             json=params, timeout=40).json()
    except requests.RequestException as exc:
        return {"ok": False, "description": str(exc)}


def _reply(chat_id, text: str) -> None:
    _api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
         disable_web_page_preview=True)


def _load_offset() -> int:
    try:
        with open(_OFFSET_FILE, encoding="utf-8") as fh:
            return int(json.load(fh).get("offset", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def _save_offset(offset: int) -> None:
    with open(_OFFSET_FILE, "w", encoding="utf-8") as fh:
        json.dump({"offset": offset}, fh)


def _is_private(chat: dict) -> bool:
    return chat.get("type") == "private"


def _authorised(chat: dict) -> bool:
    """Only the private chats we already send alerts to may give orders."""
    return _is_private(chat) and str(chat.get("id")) in config.TELEGRAM_CHAT_IDS


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

HELP = """<b>FirstCry bot commands</b>

/status — what can be delivered right now
/cart — everything in the cart
/health — how old each login is
/pause — stop watching
/resume — start watching again
/session — refresh a login

<b>Refreshing a login</b>
1. Log in to FirstCry in any browser
2. Open checkout.firstcry.com/pay
3. F12 → Network → F5 → right-click the first row → Copy as cURL
4. Send: <code>/session</code> then paste

For a named account: <code>/session SAI</code> then paste."""


def cmd_status(chat_id, cart_only: bool = False) -> None:
    accounts = config.load_accounts()
    if not accounts:
        _reply(chat_id, "No accounts configured.")
        return
    for account in accounts:
        try:
            cart = fa.fetch_cart(fa.load_cookies(account.session_file))
        except fa.SessionExpired:
            _reply(chat_id, f"⚠️ <b>{account.name}</b>: login expired. "
                            f"Send /session to fix it.")
            continue
        except requests.RequestException as exc:
            _reply(chat_id, f"⚠️ <b>{account.name}</b>: FirstCry unreachable "
                            f"({exc.__class__.__name__}).")
            continue

        deliverable = [c for c in cart if c["deliverable"]]
        if cart_only:
            lines = [f"📋 <b>{account.name} — {len(cart)} in cart</b>\n"]
            for c in cart:
                mark = "🟢" if c["deliverable"] else "⚪"
                lines.append(f"{mark} {c['name'][:46]}")
            _reply(chat_id, "\n".join(lines)[:4000])
        else:
            notifier.send_status(deliverable, len(cart) - len(deliverable),
                                 account.pincode, account=account.name)


def cmd_health(chat_id) -> None:
    accounts = config.load_accounts()
    if not accounts:
        _reply(chat_id, "No accounts configured.")
        return
    lines = ["🩺 <b>Login health</b>\n"]
    for a in accounts:
        lines.append(f"<b>{a.name}</b>\n{session_health.status(a)}\n")
    state = "PAUSED" if paused.is_set() else "watching"
    lines.append(f"Bot is currently <b>{state}</b>.")
    _reply(chat_id, "\n".join(lines))


def cmd_session(chat_id, argument: str) -> None:
    """Refresh a login from a pasted cURL."""
    if not argument.strip():
        _reply(chat_id, "Send the cURL with it, like:\n"
                        "<code>/session curl 'https://checkout...'</code>\n\n"
                        "See /help for how to copy it.")
        return

    # An optional account name may come first: "/session SAI curl '...'"
    account_name = None
    stripped = argument.strip()
    first, _, rest = stripped.partition(" ")
    known = {a.name for a in config.load_accounts()}
    if first in known:
        account_name, stripped = first, rest

    cookie_str = import_cookies.extract_cookie_string(stripped)
    if not cookie_str:
        _reply(chat_id, "❌ Couldn't find a Cookie header in that.\n\n"
                        "Use <b>Copy as cURL</b> from the Network tab on "
                        "checkout.firstcry.com/pay, then paste the whole thing.")
        return

    cookies = import_cookies.parse_cookies(cookie_str)
    names = {c["name"] for c in cookies}
    if "FC_AUTH" not in names:
        _reply(chat_id, "❌ No FC_AUTH cookie in that paste — it looks like "
                        "you copied the request before logging in.")
        return

    accounts = config.load_accounts()
    if account_name:
        target = next(a.session_file for a in accounts if a.name == account_name)
    elif len(accounts) == 1:
        target = accounts[0].session_file
        account_name = accounts[0].name
    elif accounts:
        _reply(chat_id, "Several accounts exist — say which:\n"
                        + "\n".join(f"<code>/session {a.name}</code> …"
                                    for a in accounts))
        return
    else:
        config.ACCOUNTS_DIR.mkdir(exist_ok=True)
        account_name = "SAI"
        target = config.ACCOUNTS_DIR / "SAI.json"

    with open(target, "w", encoding="utf-8") as fh:
        json.dump({"cookies": cookies, "origins": []}, fh, indent=2)

    # Prove it works before claiming success.
    try:
        cart = fa.fetch_cart(fa.load_cookies(target))
    except fa.SessionExpired:
        _reply(chat_id, f"⚠️ Saved {len(cookies)} cookies for "
                        f"<b>{account_name}</b>, but FirstCry still says "
                        f"logged out. Make sure you were signed in when you "
                        f"copied the request.")
        return
    except requests.RequestException:
        _reply(chat_id, f"✅ Saved {len(cookies)} cookies for "
                        f"<b>{account_name}</b>, but couldn't reach FirstCry "
                        f"to verify. The bot will pick it up shortly.")
        return

    deliverable = sum(1 for c in cart if c["deliverable"])
    log(f"session refreshed for {account_name} via Telegram")
    _reply(chat_id, f"✅ <b>Login refreshed — {account_name}</b>\n\n"
                    f"{len(cookies)} cookies saved and verified.\n"
                    f"Cart: {len(cart)} items, {deliverable} deliverable.\n\n"
                    f"Watching resumes automatically.")


def handle(message: dict) -> None:
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return

    command, _, argument = text.partition(" ")
    command = command.split("@")[0].lower()   # strip @botname in groups
    chat_id = chat.get("id")

    if not _authorised(chat):
        if _is_private(chat):
            log(f"ignored command from unauthorised chat {chat_id}")
        elif command in ("/status", "/help", "/health"):
            _reply(chat_id, "Commands only work in a private chat with me — "
                            "a session paste in a group would leak the login.")
        return

    log(f"{command} from {chat_id}")

    if command == "/help" or command == "/start":
        _reply(chat_id, HELP)
    elif command == "/status":
        cmd_status(chat_id)
    elif command == "/cart":
        cmd_status(chat_id, cart_only=True)
    elif command == "/health":
        cmd_health(chat_id)
    elif command == "/session":
        cmd_session(chat_id, argument)
    elif command == "/pause":
        paused.set()
        _reply(chat_id, "⏸ Paused. Nothing will be checked until /resume.")
    elif command == "/resume":
        paused.clear()
        _reply(chat_id, "▶️ Watching again.")
    else:
        _reply(chat_id, f"Don't know {command}. Try /help.")


# --------------------------------------------------------------------------

def listen(stop: threading.Event) -> None:
    """Long-poll Telegram for commands until told to stop."""
    if not config.telegram_ready():
        log("Telegram not configured - command listener not starting.")
        return

    offset = _load_offset()
    log("listening for commands (/help for the list)")

    while not stop.is_set():
        data = _api("getUpdates", offset=offset, timeout=25)
        if not data.get("ok"):
            # Usually a network hiccup; back off rather than spin.
            time.sleep(5)
            continue

        for update in data.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message") or update.get("edited_message")
            if not message:
                continue
            try:
                handle(message)
            except Exception as exc:
                log(f"error handling command: {exc}")
        _save_offset(offset)
