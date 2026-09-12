"""Telegram alerts, formatted to be read on a phone at a glance.

Design rules kept deliberately simple:
  - one clear headline, then a blank line
  - each product is a numbered block, never a wall of text
  - product name is the tappable link, on its own line
  - one compact meta line underneath: price - stock - eta
  - nothing else competing for attention
"""
import html
import sys

import requests

import config

_API = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram's hard limit is 4096 characters; leave headroom for the header.
_MAX_CHARS = 3600


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

def _name(text: str, limit: int = 62) -> str:
    text = " ".join((text or "").split())
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return html.escape(text)


def _rupees(value) -> str:
    """299 -> '₹299', 269.1 -> '₹269'."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return ""
    return f"₹{int(round(n)):,}"


def _price_bit(price, mrp, discount) -> str:
    """'₹269  (was ₹299, -10%)' or just '₹299'."""
    now = _rupees(price if price not in (None, "") else mrp)
    if not now:
        return ""
    try:
        has_disc = float(discount or 0) > 0 and float(mrp or 0) > float(price or 0)
    except (TypeError, ValueError):
        has_disc = False
    if has_disc:
        return f"{now}  <s>{_rupees(mrp)}</s> −{int(float(discount))}%"
    return now


def _date_bit(raw) -> str:
    """'2026-09-14T00:00:00' -> '14 Sep'."""
    if not raw:
        return ""
    text = str(raw)[:10]
    try:
        y, m, d = text.split("-")
        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        return f"{int(d)} {months[int(m) - 1]}"
    except (ValueError, IndexError):
        return text


def _meta(parts: list[str]) -> str:
    """Join the non-empty bits with a middot separator."""
    return "  ·  ".join(p for p in parts if p)


def _block(index: int, name: str, url: str, meta: str, note: str = "") -> str:
    out = f"\n<b>{index}.</b> <a href=\"{url}\">{_name(name)}</a>\n"
    if meta:
        out += f"     {meta}\n"
    if note:
        out += f"     {note}\n"
    return out


# --------------------------------------------------------------------------
# Bot 1 - new arrivals and restocks
# --------------------------------------------------------------------------

def send_new_products(new_items: list[dict],
                      restocked: list[dict] | None = None) -> None:
    restocked = restocked or []
    if not new_items and not restocked:
        return

    if new_items and restocked:
        title = f"{len(new_items)} new  ·  {len(restocked)} back in stock"
    elif new_items:
        title = f"{len(new_items)} new Hot Wheels" if len(new_items) > 1 else "New Hot Wheels"
    else:
        title = (f"{len(restocked)} back in stock" if len(restocked) > 1
                 else "Back in stock")

    header = f"🚨 <b>{title}</b>\n"

    blocks = []
    if new_items:
        blocks.append("\n<b>NEW LISTINGS</b>\n")
        for i, p in enumerate(new_items, 1):
            meta = _meta([_price_bit(p.get("discounted_price"), p.get("price"),
                                     p.get("discount")),
                          f"{p.get('stock')} in stock"])
            blocks.append(_block(i, p["name"], p["url"], meta))
    if restocked:
        blocks.append("\n<b>BACK IN STOCK</b>\n")
        for i, p in enumerate(restocked, 1):
            meta = _meta([_price_bit(p.get("discounted_price"), p.get("price"),
                                     p.get("discount")),
                          f"{p.get('stock')} in stock"])
            blocks.append(_block(i, p["name"], p["url"], meta))

    _send_blocks(header, blocks)


# --------------------------------------------------------------------------
# Bot 2 - cart deliverability and wishlist restocks
# --------------------------------------------------------------------------

def send_deliverable(items: list[dict], pincode: str) -> None:
    """The headline alert: cart items you can finally order."""
    if not items:
        return
    what = "item is" if len(items) == 1 else f"{len(items)} items are"
    header = (f"🟢 <b>Deliverable now</b>\n"
              f"<i>{what} now shippable to {pincode}</i>\n")

    blocks = []
    for i, it in enumerate(items, 1):
        meta = _meta([_price_bit(it.get("price"), it.get("mrp"), it.get("discount")),
                      f"{it.get('servicable')} in stock",
                      f"by {_date_bit(it.get('eta'))}" if it.get("eta") else ""])
        blocks.append(_block(i, it["name"], it["url"], meta))

    footer = "\n➡️ <a href=\"https://checkout.firstcry.com/pay\">Open cart</a>\n"
    _send_blocks(header, blocks, footer)


def send_back_in_stock(items: list[dict]) -> None:
    """Wishlist items that are available again."""
    if not items:
        return
    what = "item" if len(items) == 1 else "items"
    header = f"🔄 <b>{len(items)} wishlist {what} back in stock</b>\n"

    blocks = []
    for i, it in enumerate(items, 1):
        meta = _meta([_price_bit(it.get("price"), it.get("mrp"), None),
                      f"{it.get('stock')} in stock"])
        note = ""
        added = it.get("added")
        if added == "added to cart":
            note = "🛒 <b>Added to your cart</b>"
        elif added == "already in cart":
            note = "🛒 already in cart"
        elif added:
            note = f"⚠️ {html.escape(str(added))}"
        blocks.append(_block(i, it["name"], it["url"], meta, note))

    footer = "\n➡️ <a href=\"https://checkout.firstcry.com/pay\">Open cart</a>\n"
    _send_blocks(header, blocks, footer)


def send_status(deliverable: list[dict], waiting: int, pincode: str,
                title: str = "Cart status") -> None:
    """A snapshot of where things stand right now.

    Unlike the alerts, this reports current state rather than a change - for
    when you want to see what's orderable without waiting for something to
    flip.
    """
    header = (f"📋 <b>{title}</b>\n"
              f"<i>{len(deliverable)} deliverable to {pincode}"
              f"{f', {waiting} still waiting' if waiting else ''}</i>\n")

    if not deliverable:
        send(header + "\nNothing is deliverable right now. Still watching.")
        return

    blocks = []
    for i, it in enumerate(deliverable, 1):
        meta = _meta([_price_bit(it.get("price"), it.get("mrp"), it.get("discount")),
                      f"{it.get('servicable')} in stock",
                      f"by {_date_bit(it.get('eta'))}" if it.get("eta") else ""])
        blocks.append(_block(i, it["name"], it["url"], meta))

    footer = "\n➡️ <a href=\"https://checkout.firstcry.com/pay\">Open cart</a>\n"
    _send_blocks(header, blocks, footer)


def send_session_expired() -> None:
    send("⚠️ <b>FirstCry session expired</b>\n\n"
         "Bot 2 has stopped watching.\n\n"
         "To fix, run:\n<code>python import_cookies.py</code>")
