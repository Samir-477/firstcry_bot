"""Bot 1 - tells you when a NEW Hot Wheels item is added to FirstCry.

Keeps a memory file of every product ID it has ever seen. Anything not in that
file is new. The very first run only builds the memory and stays silent,
otherwise you'd get alerted about all 142 existing products at once.

    python bot1_new_arrivals.py            # check once, then exit
    python bot1_new_arrivals.py --loop     # keep running, check once a day
    python bot1_new_arrivals.py --reset    # forget memory and re-seed
"""
import argparse
import json
import sys
import time
from datetime import datetime

import config
import firstcry_api
import notifier


def load_state() -> tuple[set[str], set[str]]:
    """Returns (ever_seen, live_at_last_check).

    ever_seen  - every product ID we have ever laid eyes on
    live_last  - the IDs that were actually listed during the previous check

    We need both because FirstCry hides out-of-stock products. A product that
    sells out disappears, then reappears on restock. Without `live_last` we
    would report every restock as a brand-new listing.
    """
    if not config.SEEN_PRODUCTS_FILE.exists():
        return set(), set()
    try:
        with open(config.SEEN_PRODUCTS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return set(data.get("pids", [])), set(data.get("live", []))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[bot1] Could not read memory file ({exc}); treating as empty.")
        return set(), set()


def save_state(ever_seen: set[str], live_now: set[str]) -> None:
    payload = {"updated": datetime.now().isoformat(timespec="seconds"),
               "pids": sorted(ever_seen),
               "live": sorted(live_now)}
    with open(config.SEEN_PRODUCTS_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def check_once() -> int:
    """One full check. Returns how many new products were found."""
    log(f"Checking brand {config.BRAND_ID} for pincode {config.PINCODE}...")
    try:
        products = firstcry_api.fetch_products(config.BRAND_ID, config.PINCODE)
    except Exception as exc:
        log(f"ERROR fetching products: {exc}")
        return 0

    if not products:
        log("API returned nothing. Skipping so we don't wipe the memory file.")
        return 0

    ever_seen, live_last = load_state()
    live_now = {p["pid"] for p in products}
    first_run = not ever_seen

    if first_run:
        save_state(live_now, live_now)
        log(f"First run - memorised {len(products)} products. No alerts sent.")
        log("From the next check onwards you'll only hear about newly added items.")
        return 0

    # Only genuinely new listings - products never seen on FirstCry before.
    # Restocks of things we've already seen are deliberately ignored: Bot 2
    # handles anything you actually care about owning.
    new_items = [p for p in products if p["pid"] not in ever_seen]

    log(f"Found {len(products)} listed | {len(new_items)} newly added")

    for p in new_items:
        log(f"  NEW: {p['pid']} - {p['name'][:55]} (Rs{p['price']}, stock {p['stock']})")

    if new_items:
        notifier.send_new_products(new_items)

    save_state(ever_seen | live_now, live_now)
    return len(new_items)


def main() -> int:
    ap = argparse.ArgumentParser(description="FirstCry new-arrivals watcher")
    ap.add_argument("--loop", action="store_true",
                    help=f"run forever, checking every {config.BOT1_INTERVAL_HOURS}h")
    ap.add_argument("--reset", action="store_true",
                    help="delete the memory file and re-seed from scratch")
    args = ap.parse_args()

    if args.reset and config.SEEN_PRODUCTS_FILE.exists():
        config.SEEN_PRODUCTS_FILE.unlink()
        log("Memory cleared.")

    if not config.telegram_ready():
        log("WARNING: Telegram not configured in .env - alerts will print here only.")

    if not args.loop:
        check_once()
        return 0

    interval = config.BOT1_INTERVAL_HOURS * 3600
    log(f"Loop mode: checking every {config.BOT1_INTERVAL_HOURS} hour(s). Ctrl+C to stop.")
    while True:
        try:
            check_once()
        except KeyboardInterrupt:
            log("Stopped.")
            return 0
        except Exception as exc:
            log(f"Unexpected error, will retry next cycle: {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
