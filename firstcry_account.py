"""Logged-in FirstCry client: reads your shortlist and cart, and edits the cart.

Uses the session cookies saved by import_cookies.py. No password is ever
involved. Nothing here buys anything - adding to and removing from the cart
is as far as the writes go.

Endpoints were found by reading FirstCry's own front-end JavaScript:
  shortlist -> POST https://www.firstcry.com/api/shortlist  (myshortlist.min.1.6.js)
  cart read -> GET  https://checkout.firstcry.com/pay       (embedded JSON)
  cart write-> POST /svcs/CommonService.svc/SaveCartDetail  (cart-deployment.js)
"""
import json
import urllib.parse
from pathlib import Path

import requests

import config
from firstcry_api import product_url

SHORTLIST_API = "https://www.firstcry.com/api/shortlist"
CART_PAGE = "https://checkout.firstcry.com/pay"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


class SessionExpired(RuntimeError):
    """Raised when FirstCry no longer accepts the saved cookies."""


def load_cookies(path: Path | None = None) -> dict[str, str]:
    path = path or config.SESSION_FILE
    if not path.exists():
        raise SessionExpired(
            f"{path.name} not found - run import_cookies.py to set up your session.")
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    cookies = {c["name"]: c["value"] for c in state.get("cookies", [])}
    if not cookies:
        raise SessionExpired("Session file has no cookies in it.")
    return cookies


def _cookie(cookies: dict[str, str], name: str) -> str:
    return urllib.parse.unquote(cookies.get(name, ""))


# --------------------------------------------------------------------------
# Wishlist
# --------------------------------------------------------------------------

def fetch_wishlist(cookies: dict[str, str], pincode: str | None = None) -> list[dict]:
    """Every product on your shortlist, with live stock and pricing."""
    pincode = pincode or config.PINCODE
    saved = _cookie(cookies, "FC_product_saved")
    boost = ",".join(x for x in saved.split(",") if x.strip() and x.strip() != "0")

    body = {
        "ftk": _cookie(cookies, "FC_AUTH"),
        "boostProductIds": boost,
        "type": "shortlist",
        "isclub": "0",
        "pcode": int(pincode),
    }
    headers = {**HEADERS,
               "Content-Type": "application/json; charset=utf-8",
               "Referer": "https://www.firstcry.com/myshortlist",
               "X-Requested-With": "XMLHttpRequest"}

    resp = requests.post(SHORTLIST_API, data=json.dumps(body),
                         cookies=cookies, headers=headers, timeout=40)
    resp.raise_for_status()
    data = resp.json()

    out = []
    for p in data.get("products") or []:
        stock = p.get("stock") or {}
        pricing = p.get("pricing") or {}
        out.append({
            "pid": str(p.get("id", "")),
            "name": (p.get("name") or "").strip(),
            "stock": stock.get("current", 0) if isinstance(stock, dict) else 0,
            "mrp": pricing.get("mrp"),
            "price": pricing.get("discPrice"),
            "pricedrop": p.get("pricedrop", 0),
            "url": product_url(p.get("id"), p.get("name", ""),
                               (p.get("brand") or {}).get("name", "")),
        })
    return out


# --------------------------------------------------------------------------
# Cart - this is where deliverability lives
# --------------------------------------------------------------------------

def _extract_cart_json(html: str) -> list[dict]:
    """The checkout page embeds the cart as a "PurchaseOrderItemList" array."""
    i = html.find('"PurchaseOrderItemList"')
    if i < 0:
        return []
    start = html.find("[", i)
    if start < 0:
        return []
    try:
        items, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError:
        return []
    return items if isinstance(items, list) else []


def fetch_cart(cookies: dict[str, str]) -> list[dict]:
    """Everything in your cart, with the per-item deliverability flag.

    IsServicable is the key field:
        0        -> cannot be delivered to your pincode
        above 0  -> deliverable (the number is servicable warehouse stock)
    """
    headers = {**HEADERS,
               "Accept": "text/html,application/xhtml+xml",
               "Referer": "https://www.firstcry.com/"}
    resp = requests.get(CART_PAGE, cookies=cookies, headers=headers,
                        timeout=40, allow_redirects=True)
    resp.raise_for_status()

    html = resp.text
    if "login" in resp.url.lower() or not ("Logout" in html or "logout" in html):
        raise SessionExpired("FirstCry bounced us to login - session has expired.")

    out = []
    for it in _extract_cart_json(html):
        serv = it.get("IsServicable")
        out.append({
            "pid": str(it.get("ProductID") or it.get("ProductId") or ""),
            "name": (it.get("ProductName") or "").strip(),
            "servicable": serv,
            "deliverable": serv not in (0, "0", None, ""),
            "stock": it.get("CurrentStock"),
            "quantity": it.get("Quantity"),
            "eta": it.get("EstimatedDeliveryDate") or "",
            "cod": it.get("IsCodAvailableToPincode"),
            "mrp": it.get("MRP"),
            "price": it.get("ActualPrice"),
            "discount": it.get("DiscountInPer"),
            "url": product_url(it.get("ProductID"),
                               it.get("ProductName", ""),
                               it.get("BrandName", "")),
        })
    return out


# --------------------------------------------------------------------------
# Cart writes
# --------------------------------------------------------------------------
# Note: FirstCry also exposes /tatapi/oam/checkdeliveryinfo, which looks like
# it answers "can this reach my pincode" without touching the cart. It was
# tried and removed - it returned 0 three times running for a product the
# cart was actively shipping. fetch_cart() above is the only reliable source.

SAVE_CART_API = "https://www.firstcry.com/svcs/CommonService.svc/SaveCartDetail"
PDP_CART_API = "https://www.firstcry.com/capinet/pdp/SaveProductCart"


def _cart_write(cookies: dict[str, str], pid: str, action: str,
                quantity: int = 1) -> tuple[bool, str]:
    """Add to or remove from the cart. action is "add" or "remove"."""
    body = {
        "ftk": _cookie(cookies, "FC_AUTH"),
        "viewid": "",
        "productid": str(pid),
        "quantity": str(quantity),
        "offertype": "NO",
        "offerid": "",
        "action": action,
        "gcoffer": "",
    }
    headers = {
        **HEADERS,
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://www.firstcry.com",
        "Referer": f"https://www.firstcry.com/product-detail/{pid}",
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        resp = requests.post(SAVE_CART_API, data=json.dumps(body),
                             cookies=cookies, headers=headers, timeout=40)
    except requests.RequestException as exc:
        return False, f"network error: {exc}"

    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    return True, (resp.text or "")[:300]


def add_to_cart(cookies: dict[str, str], pid: str,
                quantity: int = 1) -> tuple[bool, str]:
    """Put one product into your cart. Returns (worked, message).

    Mirrors what the site's own "Add to Cart" button does: the real cart write
    is SaveCartDetail; SaveProductCart is fired alongside it (the site does the
    same) and is best-effort only.
    """
    ok, msg = _cart_write(cookies, pid, "add", quantity)

    # The website also pings this one. Failure here doesn't undo the add.
    try:
        requests.post(
            PDP_CART_API,
            data=json.dumps({"objdd": {"ProductID": str(pid), "ViewID": "",
                                       "ProductType": "product", "cart": "cart",
                                       "Discount": ""},
                             "ftk": _cookie(cookies, "FC_AUTH")}),
            cookies=cookies,
            headers={**HEADERS, "Content-Type": "application/json",
                     "Origin": "https://www.firstcry.com",
                     "Referer": f"https://www.firstcry.com/product-detail/{pid}"},
            timeout=20)
    except requests.RequestException:
        pass

    return ok, msg


def remove_from_cart(cookies: dict[str, str], pid: str) -> tuple[bool, str]:
    """Take one product back out of the cart."""
    return _cart_write(cookies, pid, "remove")
