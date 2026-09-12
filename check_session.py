"""Answers one question: is the saved session still logged in to FirstCry?

Run this any time. No browser needed - it just replays your saved cookies the
same way Bot 2 will, and reports what FirstCry says back.

    python check_session.py
"""
import json
import sys
import time

import requests

import config

SHORTLIST_URL = "https://www.firstcry.com/myshortlist"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# If we get bounced to any of these, the session is dead.
LOGGED_OUT_MARKERS = ("/login", "signin", "sign-in", "returnurl")


def load_cookies() -> dict[str, str]:
    """Pull cookies out of the Playwright storage_state file."""
    if not config.SESSION_FILE.exists():
        return {}
    with open(config.SESSION_FILE, encoding="utf-8") as fh:
        state = json.load(fh)
    return {c["name"]: c["value"] for c in state.get("cookies", [])
            if "firstcry" in c.get("domain", "")}


def check() -> bool:
    """True if the session still works. Prints a human explanation either way."""
    if not config.SESSION_FILE.exists():
        print("NOT LOGGED IN - session.json does not exist yet.")
        print("   Fix: run  python login_once.py")
        return False

    cookies = load_cookies()
    if not cookies:
        print("NOT LOGGED IN - session.json has no FirstCry cookies in it.")
        print("   Fix: run  python login_once.py  and log in fully before pressing Enter.")
        return False

    # Cookies imported from a cURL paste carry no expiry dates, so age is
    # the only clue we have about how close this session is to dying.
    age_days = (time.time() - config.SESSION_FILE.stat().st_mtime) / 86400
    print(f"Session file is {age_days:.1f} days old ({len(cookies)} FirstCry cookies).")
    print("Testing it against your shortlist...")

    try:
        resp = requests.get(SHORTLIST_URL, cookies=cookies, headers=HEADERS,
                            timeout=30, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"Could not reach FirstCry: {exc}")
        return False

    final_url = resp.url.lower()
    bounced = any(m in final_url for m in LOGGED_OUT_MARKERS)

    if bounced:
        print("SESSION EXPIRED - FirstCry redirected us to the login page.")
        print(f"   Landed on: {resp.url}")
        print("   Fix: run  python login_once.py  again.")
        return False

    print("LOGGED IN - the shortlist page loaded without redirecting to login.")
    print(f"   Final URL: {resp.url}")
    print(f"   Page size: {len(resp.text):,} bytes")
    print("\nThis is exactly how Bot 2 will authenticate. No password involved.")
    return True


if __name__ == "__main__":
    sys.exit(0 if check() else 1)
