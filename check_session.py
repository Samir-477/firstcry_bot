"""Answers one question: are the saved logins still working?

Run this any time. No browser needed - it just replays your saved cookies the
same way Bot 2 does, and reports what FirstCry says back.

Checks every account in accounts/, falling back to a single session.json if
that folder is empty.

    python check_session.py
"""
import sys

import requests

import config
import firstcry_account as fa
import session_health

SHORTLIST_URL = "https://www.firstcry.com/myshortlist"

# If we get bounced to any of these, the session is dead.
LOGGED_OUT_MARKERS = ("/login", "signin", "sign-in", "returnurl")


def check_account(account: config.Account) -> bool:
    """True if this account's session still works."""
    print(f"--- {account.name} ---")

    try:
        cookies = fa.load_cookies(account.session_file)
    except fa.SessionExpired as exc:
        print(f"   NOT LOGGED IN - {exc}")
        return False

    print(f"   {session_health.status(account)}")
    print(f"   {len(cookies)} cookies. Testing against your shortlist...")

    headers = {**fa.HEADERS, "Accept": "text/html,application/xhtml+xml"}
    try:
        resp = requests.get(SHORTLIST_URL, cookies=cookies, headers=headers,
                            timeout=30, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"   Could not reach FirstCry: {exc}")
        return False

    if any(m in resp.url.lower() for m in LOGGED_OUT_MARKERS):
        print("   SESSION EXPIRED - FirstCry redirected us to the login page.")
        print(f"   Fix: python import_cookies.py --account {account.name}")
        return False

    print(f"   LOGGED IN - shortlist loaded ({len(resp.text):,} bytes)")

    # The cart is what Bot 2 actually watches, so check that too.
    try:
        cart = fa.fetch_cart(cookies)
        deliverable = sum(1 for c in cart if c["deliverable"])
        print(f"   Cart: {len(cart)} items, {deliverable} deliverable "
              f"to {account.pincode}")
    except fa.SessionExpired:
        print("   ...but the cart says logged out. Session is on its way out.")
        return False
    except requests.RequestException as exc:
        print(f"   (cart unreachable right now: {exc})")

    return True


def main() -> int:
    accounts = config.load_accounts()
    if not accounts:
        print("No accounts configured.")
        print("Create one with:  python import_cookies.py --account NAME")
        return 1

    results = [check_account(a) for a in accounts]
    print()
    good = sum(results)
    print(f"{good} of {len(results)} account(s) logged in.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
