"""Telegram alerts, written to be understood in one glance on a phone.

Design rules:
  - the headline says what to DO, not what the bot did
  - one product per card: name, price, urgency, delivery date
  - stock is translated into plain language ("Only 2 left" beats "serv=2")
  - exactly one call to action, at the bottom, impossible to miss
  - nothing else competing for attention
"""
import html
import sys

import requests

import config

_API = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram's hard limit is 4096 characters; leave headroom for the header.
_MAX_CHARS = 3600

CART_URL = "https://checkout.firstcry.com/pay"
SHORTLIST_URL = "https://www.firstcry.com/myshortlist"
# FirstCry has no clean /hot-wheels brand page - both the obvious guesses
# (/hot-wheels/... and /brand/hot-wheels) 404. Search is what actually works.
BROWSE_URL = "https://www.firstcry.com/searchresult?searchstring=hot%20wheels"


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------

def _send_to(chat_id: str, text: str) -> bool:
    try:
        resp = requests.post(
            _API.format(token=config.TELEGRAM_BOT_TOKEN),
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"[notifier] Telegram error for chat {chat_id} "
                  f"({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
            return False
        return True
    except requests.RequestException as exc:
        print(f"[notifier] Telegram unreachable for chat {chat_id}: {exc}",
              file=sys.stderr)
        return False


def send(text: str) -> bool:
    """Send to every configured recipient. One bad chat never blocks the rest."""
    if not config.telegram_ready():
        print("[notifier] Telegram not configured -- printing instead:\n" + text,
              file=sys.stderr)
        return False
    return any([_send_to(cid, text) for cid in config.TELEGRAM_CHAT_IDS])


def _send_blocks(header: str, blocks: list[str], footer: str = "") -> None:
    """Send header + blocks, splitting into several messages if too long."""
    if not blocks:
        return
    current, chunks = header, []
    for block in blocks:
        if len(current) + len(block) > _MAX_CHARS:
            chunks.append(current)
            current = header
        current += block
    chunks.append(current + footer if footer else current)
    for chunk in chunks:
        send(chunk)


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def _who(account: str | None) -> str:
    """Label which account an alert is about, but stay quiet when there is
    only one - no point putting "default" on every message."""
    return f" · {html.escape(account)}" if account and account != "default" else ""


def _name(text: str, limit: int = 58) -> str:
    text = " ".join((text or "").split())
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return html.escape(text)


def _rupees(value) -> str:
    """299 -> '₹299', 269.1 -> '₹269'."""
    try:
        return f"₹{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return ""


def _price_line(item: dict) -> str:
    """'₹809  ₹899  −10% off' or just '₹299'."""
    price = item.get("price")
    mrp = item.get("mrp") if item.get("mrp") is not None else item.get("price")
    discount = item.get("discount")

    now = _rupees(price if price not in (None, "") else mrp)
    if not now:
        return ""
    try:
        discounted = (float(discount or 0) > 0
                      and float(mrp or 0) > float(price or 0))
    except (TypeError, ValueError):
        discounted = False
    if discounted:
        return (f"<b>{now}</b>  <s>{_rupees(mrp)}</s>  "
                f"−{int(float(discount))}% off")
    return f"<b>{now}</b>"


def _date(raw) -> str:
    """'2026-09-14T00:00:00' -> '14 Sep'."""
    if not raw:
        return ""
    text = str(raw)[:10]
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    try:
        _, m, d = text.split("-")
        return f"{int(d)} {months[int(m) - 1]}"
    except (ValueError, IndexError):
        return text


def _urgency(stock) -> str:
    """Translate a stock number into how urgently you should move.

    "447 in stock" and "2 in stock" mean very different things when you are
    deciding whether to drop what you're doing, so say which it is.
    """
    try:
        n = int(stock)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n <= 3:
        return f"🔥 Only {n} left"
    if n <= 15:
        return f"⚠️ {n} left"
    return f"📦 {n} in stock"


def _card(item: dict, index: int | None = None,
          stock_key: str = "servicable") -> str:
    """One product, laid out to be read at a glance."""
    label = f"{index}. " if index is not None else ""
    out = f"\n<b>{label}<a href=\"{item['url']}\">{_name(item['name'])}</a></b>\n"

    price = _price_line(item)
    if price:
        out += price + "\n"

    bits = []
    urgency = _urgency(item.get(stock_key) or item.get("stock"))
    if urgency:
        bits.append(urgency)
    if item.get("eta"):
        bits.append(f"🚚 by {_date(item['eta'])}")
    if bits:
        out += "  ·  ".join(bits) + "\n"

    if item.get("added"):
        out += f"🛒 {html.escape(str(item['added']))}\n"
    return out


def _cta(text: str, url: str) -> str:
    return f"\n<b>👉 <a href=\"{url}\">{text}</a></b>\n"


# --------------------------------------------------------------------------
# Bot 1 - new listings
# --------------------------------------------------------------------------

def send_new_products(new_items: list[dict],
                      restocked: list[dict] | None = None) -> None:
    """Bot 1: Hot Wheels that were not on FirstCry before."""
    restocked = restocked or []
    if not new_items and not restocked:
        return

    count = len(new_items) + len(restocked)
    what = "NEW HOT WHEELS" if count == 1 else f"{count} NEW HOT WHEELS"
    header = (f"🚨 <b>{what}</b>\n"
              f"<i>just listed on FirstCry</i>\n")

    # Bot 1's products use different field names to the cart's.
    def normalise(p: dict) -> dict:
        return {**p,
                "price": p.get("discounted_price") or p.get("price"),
                "mrp": p.get("price"),
                "servicable": p.get("stock")}

    blocks = [_card(normalise(p), i)
              for i, p in enumerate(new_items + restocked, 1)]
    _send_blocks(header, blocks, _cta("BROWSE ALL HOT WHEELS", BROWSE_URL))


# --------------------------------------------------------------------------
# Bot 2 - deliverability
# --------------------------------------------------------------------------

def send_deliverable(items: list[dict], pincode: str,
                     account: str | None = None) -> None:
    """The one that matters: things you can actually order right now."""
    if not items:
        return
    count = "1 item" if len(items) == 1 else f"{len(items)} items"
    header = (f"🟢 <b>READY TO ORDER{_who(account)}</b>\n"
              f"<i>{count} can now be delivered to {pincode}</i>\n")
    blocks = [_card(it, i) for i, it in enumerate(items, 1)]
    _send_blocks(header, blocks, _cta("OPEN CART TO BUY", CART_URL))


def send_status(deliverable: list[dict], waiting: int, pincode: str,
                title: str = "CART STATUS", account: str | None = None) -> None:
    """A snapshot of where things stand, rather than a change."""
    header = f"📋 <b>{title.upper()}{_who(account)}</b>\n"

    if not deliverable:
        send(header
             + f"\nNothing can be delivered to {pincode} yet.\n"
             + f"\n<b>{waiting}</b> item(s) are parked in your cart and "
               f"being checked every cycle.\n"
             + "\nYou'll get a message the moment one becomes available.")
        return

    ready = "1 item" if len(deliverable) == 1 else f"{len(deliverable)} items"
    header += f"<i>{ready} ready · {waiting} still waiting</i>\n"
    blocks = [_card(it, i) for i, it in enumerate(deliverable, 1)]
    _send_blocks(header, blocks, _cta("OPEN CART TO BUY", CART_URL))


def send_session_expired(account: str | None = None) -> None:
    # Give the exact command, account and all - you'll be reading this on a
    # phone and wanting to copy it, not work out which flag to add.
    flag = f" --account {account}" if account and account != "default" else ""
    send(f"⚠️ <b>LOGIN EXPIRED{_who(account)}</b>\n\n"
         "The bot has been signed out of FirstCry and has stopped watching "
         "this account.\n\n"
         f"<b>To fix:</b>\n<code>python import_cookies.py{flag}</code>\n\n"
         "It picks the new login up on its own within 5 minutes — "
         "no restart needed.")
