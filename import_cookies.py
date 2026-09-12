"""Import your FirstCry session from your own browser - no automation at all.

You log in normally in whatever browser you already use. Then you copy one
request out of DevTools and paste it here. That's it.

This sidesteps reCAPTCHA entirely, because no script ever touches the login
page - you did the login yourself, like a normal person.

    python import_cookies.py
"""
import argparse
import json
import re
import sys

import config

DOMAIN = ".firstcry.com"

INSTRUCTIONS = """
======================================================================
 IMPORT YOUR FIRSTCRY SESSION
======================================================================

 In your NORMAL browser (the one you use every day):

   1. Log in to firstcry.com as usual
   2. Go to  https://www.firstcry.com/myshortlist
   3. Press F12 to open DevTools
   4. Click the "Network" tab
   5. Press F5 to reload the page
   6. Click the FIRST request in the list (usually "myshortlist")
   7. Right-click it -> Copy -> "Copy as cURL (bash)"

 Then paste it below and press Enter twice.

 (Alternatively: DevTools -> Application -> Cookies -> firstcry.com,
  and paste just the cookie string like "name1=value1; name2=value2")
======================================================================
"""


def read_paste() -> str:
    """Read a multi-line paste until a blank line or EOF."""
    print("\n>>> Paste here, then press Enter twice:\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "" and lines:
            break
        lines.append(line)
    return "\n".join(lines)


def extract_cookie_string(blob: str) -> str | None:
    """Pull the Cookie header out of a cURL command, or accept a raw string."""
    # curl -H 'cookie: a=1; b=2'  /  -H "Cookie: a=1; b=2"
    m = re.search(r"""-H\s+['"]cookie:\s*(.+?)['"]""", blob, re.I | re.S)
    if m:
        return m.group(1).strip()
    # curl -b 'a=1; b=2'
    m = re.search(r"""-b\s+['"](.+?)['"]""", blob, re.S)
    if m:
        return m.group(1).strip()
    # Raw "a=1; b=2" paste
    if "=" in blob and ";" in blob and "curl" not in blob.lower():
        return blob.strip()
    # Single cookie, no semicolon
    if re.fullmatch(r"\s*[\w.-]+=[^;\s]+\s*", blob):
        return blob.strip()
    return None


def parse_cookies(cookie_str: str) -> list[dict]:
    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if not name:
            continue
        cookies.append({
            "name": name,
            "value": value,
            "domain": DOMAIN,
            "path": "/",
            "expires": -1,
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax",
        })
    return cookies


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Import a FirstCry session from your browser")
    ap.add_argument("--account", metavar="NAME",
                    help="save as accounts/NAME.json instead of session.json, "
                         "so several logins can be watched at once")
    args = ap.parse_args()

    if args.account:
        config.ACCOUNTS_DIR.mkdir(exist_ok=True)
        target = config.ACCOUNTS_DIR / f"{args.account}.json"
        print(f"\n Importing for account: {args.account}")
        print(f" Will save to: {target}")
        if target.exists():
            print(" (this will replace the existing session for that account)")
    else:
        target = config.SESSION_FILE

    print(INSTRUCTIONS)
    blob = read_paste()

    if not blob.strip():
        print(" Nothing pasted. Run again when you're ready.")
        return 1

    cookie_str = extract_cookie_string(blob)
    if not cookie_str:
        print("\n Couldn't find a Cookie header in that paste.")
        print(" Make sure you used 'Copy as cURL (bash)', or paste the raw")
        print(" cookie string in the form:  name1=value1; name2=value2")
        return 1

    cookies = parse_cookies(cookie_str)
    if not cookies:
        print("\n Found a cookie header but couldn't parse any name=value pairs.")
        return 1

    with open(target, "w", encoding="utf-8") as fh:
        json.dump({"cookies": cookies, "origins": []}, fh, indent=2)

    print(f"\n Imported {len(cookies)} cookies -> {target}")
    names = [c["name"] for c in cookies]
    print(" Cookie names:", ", ".join(names[:15]) + (" ..." if len(names) > 15 else ""))

    # Flag the ones that look like real login tokens, as a sanity check.
    auth_like = [n for n in names
                 if any(k in n.lower() for k in ("auth", "token", "login", "user", "sess", "cust"))]
    if auth_like:
        print(" Login-ish cookies spotted:", ", ".join(auth_like))
    else:
        print(" WARNING: none of these look like login tokens. You may have")
        print(" copied the request before logging in. Check with:")

    if args.account:
        print(f"\n Now run:  python bot2_wishlist.py --account {args.account}")
    else:
        print("\n Now run:  python check_session.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
