"""Thin client for FirstCry's internal product-listing API.

Discovered by reading their listingapi4.5.min.js: the website itself calls
/svcs/SearchResult.svc/GetSearchResultProductsPaging over plain GET and gets
back JSON. No login and no browser needed for public listings.
"""
import json
import re
import time

import requests

BASE = "https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging"


def product_url(pid, name: str = "", brand: str = "") -> str:
    """Build a working product link.

    FirstCry's real format is /<brand>/<name>/<pid>/product-detail. Only the
    pid actually matters - the two slug segments are ignored by their router -
    but we fill them in properly so the link reads sensibly when shared.
    """
    def slug(text: str, fallback: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
        return (s[:60].rstrip("-") or fallback)

    return (f"https://www.firstcry.com/{slug(brand, 'hot-wheels')}"
            f"/{slug(name, 'toy')}/{pid}/product-detail")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://www.firstcry.com/",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _params(brand_id: str, page_no: int, page_size: int, pincode: str) -> dict:
    """The endpoint is picky: every filter must be present, even when empty."""
    p = {
        "PageNo": page_no,
        "PageSize": page_size,
        "SortExpression": "NewArrivals",
        "OnSale": "", "SearchString": "", "SubCatId": "",
        "BrandId": brand_id,
        "Price": "", "Age": "", "Color": "", "OptionalFilter": "",
        "OutOfStock": "false",
        "combo": "", "discount": "", "searchwithincat": "", "ProductidQstr": "",
        "searchrank": "", "pmonths": "", "cgen": "", "PriceQstr": "",
        "DiscountQstr": "", "sorting": "", "masterbrand": "", "rating": "",
        "offer": "", "skills": "", "measurement": "", "material": "",
        "curatedcollections": "", "gender": "", "exclude": "", "premium": "",
        "pcode": pincode,
        "deliverytype": "",
    }
    for i in range(1, 16):
        p[f"Type{i}"] = ""
    return p


def _normalise(raw: dict) -> dict:
    """Flatten one API product into just the fields the bots care about."""
    pid = str(raw.get("PId", ""))
    return {
        "pid": pid,
        "name": raw.get("PNm", "").strip(),
        "brand": raw.get("BNm", ""),
        "price": raw.get("MRP", ""),
        "discount": raw.get("Disc", ""),
        "discounted_price": raw.get("discprice", ""),
        "stock": raw.get("CrntStock", "0"),
        "is_new": raw.get("newdays", "0") == "1",
        "url": product_url(pid, raw.get("PNm", ""), raw.get("BNm", "")),
    }


# FirstCry hard-caps the listing endpoint at 20 items per page, whatever
# PageSize we ask for. Asking for more just silently returns 20.
PAGE_SIZE = 20


def fetch_products(brand_id: str, pincode: str = "", page_size: int = PAGE_SIZE,
                   max_pages: int = 40, delay: float = 1.0) -> list[dict]:
    """Fetch every listed product for a brand, newest first.

    Pages politely with a delay so we never look like a scraper.
    """
    products: list[dict] = []
    seen_pids: set[str] = set()
    total_expected: int | None = None

    for page_no in range(1, max_pages + 1):
        resp = requests.get(BASE, params=_params(brand_id, page_no, page_size, pincode),
                            headers=HEADERS, timeout=40)
        resp.raise_for_status()

        # The payload is JSON-encoded twice: {"ProductResponse": "<json string>"}
        payload = json.loads(resp.json()["ProductResponse"])
        batch = payload.get("Products") or []
        if not batch:
            break

        # "Count" arrives as e.g. [142] and tells us the full catalogue size.
        if total_expected is None:
            count = payload.get("Count")
            if isinstance(count, list) and count:
                total_expected = int(count[0])
            elif isinstance(count, (int, str)) and str(count).isdigit():
                total_expected = int(count)

        fresh = 0
        for raw in batch:
            item = _normalise(raw)
            if item["pid"] and item["pid"] not in seen_pids:
                seen_pids.add(item["pid"])
                products.append(item)
                fresh += 1

        # Stop when the page repeated itself, or we've collected everything.
        if fresh == 0:
            break
        if total_expected is not None and len(products) >= total_expected:
            break
        time.sleep(delay)

    return products
