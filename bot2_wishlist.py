"""Bot 2 - keeps your shortlist in the cart and tells you what turns deliverable.

  ADD    (every few checks)
      Push any shortlist item not already in the cart. FirstCry accepts
      whatever is in stock and silently refuses the rest.

  WATCH  (every check)
      Read the cart. Each row carries IsServicable: 0 means "cannot be
      delivered to your pincode", above 0 means it can. When one flips,
      you get a Telegram.

Nothing is ever removed from the cart. Deliverability is only visible for
items sitting in it, so an item that gets taken out stops being watched.
A cart showing "Undeliverable" rows is not a bug - those are the ones
still being waited on.

FirstCry does expose /tatapi/oam/checkdeliveryinfo, which looks like it
answers the same question without the cart. It was tried and rejected: it
returned 0 three times running for an item the cart was happily shipping.
The cart is the only trustworthy source.

It never buys anything. Adding to the cart is as far as it goes.

    python bot2_wishlist.py                    # check once, then exit
    python bot2_wishlist.py --loop             # keep running
    python bot2_wishlist.py --status           # Telegram a snapshot now
    python bot2_wishlist.py --reset            # forget state and re-seed
    python bot2_wishlist.py --account SAI      # just one account

Every account in accounts/ is watched. With that folder empty it falls back
to a single session.json in the project root.
"""
import argparse
import json
import sys
import time
from datetime import datetime

import requests

import config
import firstcry_account as fa
import notifier


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_state(account: config.Account) -> dict:
    if not account.state_file.exists():
        return {}
    try:
        with open(account.state_file, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log(f"[{account.name}] Could not read state file ({exc}); "
            f"treating as empty.")
        return {}


def save_state(account: config.Account, items: dict) -> None:
    payload = {"updated": datetime.now().isoformat(timespec="seconds"),
               "account": account.name,
               "items": items}
    with open(account.state_file, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def _cart_writes(cookies, pids: list[str], action: str,
                 pace: float = 0.35, attempts: int = 3) -> set[str]:
    """Add or remove a batch of products, and actually make it stick.

    FirstCry drops cart writes when they arrive back-to-back - firing 24
    removes in a tight loop left a third of them still in the cart. So the
    writes are paced, then verified against a fresh read, and whatever
    didn't take is retried.

    Returns the set of product ids that ended up in the desired state.
    """
    want_present = action == "add"
    todo = list(pids)
    done: set[str] = set()

    for attempt in range(attempts):
        if not todo:
            break
        for pid in todo:
            if want_present:
                fa.add_to_cart(cookies, pid)
            else:
                fa.remove_from_cart(cookies, pid)
            time.sleep(pace)

        in_cart = {c["pid"] for c in fa.fetch_cart(cookies)}
        settled = [p for p in todo if (p in in_cart) == want_present]
        done.update(settled)
        todo = [p for p in todo if p not in settled]

        if todo and attempt < attempts - 1:
            log(f"      {len(settled)} of {len(settled) + len(todo)} {action}s "
                f"landed, retrying the rest")

    if todo:
        # After several paced attempts these are almost certainly out of
        # stock rather than dropped writes - FirstCry accepts the request
        # and silently declines to put the item in the cart.
        log(f"      {len(todo)} {action}(s) not accepted "
            f"(out of stock) - will try again next sweep")
    return done


def check_once(account: config.Account, state: dict,
               attempt_adds: bool = True) -> tuple[dict, int]:
    """One pass. Returns (new_state, number_of_alerts).

    The add API replies "true" whether or not an item really went in, so
    its answer is ignored; the cart is re-read to see what actually landed.
    """
    cookies = fa.load_cookies(account.session_file)

    wishlist = fa.fetch_wishlist(cookies, account.pincode)
    cart = {c["pid"]: c for c in fa.fetch_cart(cookies)}

    old = state.get("items", {})
    first_run = not old
    new_state = {pid: dict(info) for pid, info in old.items()}

    # ---- KEEP EVERYTHING IN THE CART -------------------------------------
    # Deliverability is only visible for items sitting in the cart, so every
    # shortlist item goes in and stays in. Nothing is ever removed: an item
    # that isn't in the cart can't be watched, and the alternative - taking
    # undeliverable ones out and putting them back to re-test - meant far
    # more cart writes and a slower reaction when something flipped.
    #
    # Adds run on a slower cadence than the read, because once everything is
    # in the cart there is usually nothing to add.
    added = 0
    if config.AUTO_ADD_TO_CART and attempt_adds:
        todo = [w["pid"] for w in wishlist if w["pid"] not in cart]
        if todo:
            added = len(_cart_writes(cookies, todo, "add"))
            cart = {c["pid"]: c for c in fa.fetch_cart(cookies)}
            if added:
                log(f"[{account.name}]   added {added} item(s) to the cart"
                    + (f" ({len(todo) - added} refused - out of stock)"
                       if added < len(todo) else ""))

    # ---- READ THE ANSWER OFF THE CART ------------------------------------
    # The cart's IsServicable is the ONLY trustworthy source. The
    # /tatapi/oam/checkdeliveryinfo endpoint was tried and rejected: it
    # returned 0 three times running for an item the cart was shipping.
    deliverable_now, became = [], []
    for pid, item in cart.items():
        if item["deliverable"]:
            deliverable_now.append(item)
            if not first_run and not old.get(pid, {}).get("deliverable", False):
                became.append({**item, "added": "in your cart, ready to order"})

        new_state.setdefault(pid, {})
        new_state[pid].update({"deliverable": item["deliverable"],
                               "servicable": item["servicable"],
                               "in_cart": True,
                               "name": item["name"]})

    for pid in set(new_state) - set(cart):
        new_state[pid]["in_cart"] = False

    log(f"[{account.name}] Shortlist: {len(wishlist)} | "
        f"in cart: {len(cart)} | "
        f"deliverable to {account.pincode}: {len(deliverable_now)}")

    if first_run:
        # Report what's already deliverable rather than staying silent.
        # Alerts only fire on a change, so anything deliverable at baseline
        # would otherwise never be mentioned - which looks like a broken bot.
        log(f"[{account.name}] First run - baseline saved. "
            f"{len(deliverable_now)} already deliverable, sending a snapshot.")
        notifier.send_status(deliverable_now, len(cart) - len(deliverable_now),
                             account.pincode, title="Watching your cart",
                             account=account.name)
        return new_state, 0

    for item in became:
        log(f"[{account.name}]   *** DELIVERABLE NOW: {item['pid']} - "
            f"{item['name'][:44]} (serv={item['servicable']})")

    if became:
        notifier.send_deliverable(became, account.pincode,
                                  account=account.name)

    return new_state, len(became)


def send_status(accounts: list[config.Account] | None = None) -> int:
    """Report what's currently deliverable, without waiting for a change."""
    accounts = accounts if accounts is not None else config.load_accounts()
    if not accounts:
        log("No accounts configured - run import_cookies.py first.")
        return 1

    rc = 0
    for account in accounts:
        try:
            cart = fa.fetch_cart(fa.load_cookies(account.session_file))
        except fa.SessionExpired as exc:
            log(f"[{account.name}] SESSION EXPIRED: {exc}")
            notifier.send_session_expired(account.name)
            rc = 1
            continue
        except requests.RequestException as exc:
            log(f"[{account.name}] Could not reach FirstCry: {exc}")
            rc = 1
            continue

        deliverable = [c for c in cart if c["deliverable"]]
        waiting = len(cart) - len(deliverable)

        log(f"[{account.name}] Cart: {len(cart)} items | "
            f"{len(deliverable)} deliverable | {waiting} waiting")
        for c in deliverable:
            log(f"   {c['pid']}  serv={c['servicable']}  {c['name'][:46]}")

        notifier.send_status(deliverable, waiting, account.pincode,
                             account=account.name)
    log("Status sent to Telegram.")
    return rc


def watch(account: config.Account, loop: bool) -> int:
    """Run one account, once or forever."""
    state = load_state(account)

    def one_pass(attempt_adds: bool = True) -> bool:
        """False means stop - the session is gone."""
        nonlocal state
        try:
            items, _ = check_once(account, state, attempt_adds=attempt_adds)
            state = {"items": items}
            save_state(account, items)
            return True
        except fa.SessionExpired as exc:
            log(f"[{account.name}] SESSION EXPIRED: {exc}")
            notifier.send_session_expired(account.name)
            return False
        except requests.RequestException as exc:
            log(f"[{account.name}] Network problem, will retry: {exc}")
            return True

    if not loop:
        return 0 if one_pass() else 1

    interval = config.BOT2_INTERVAL_SECONDS
    every = max(1, int(config.ADD_TO_CART_EVERY_N_CHECKS))
    log(f"[{account.name}] Loop mode: checking every {interval:g}s, "
        f"trying cart adds every {every} checks. Ctrl+C to stop.")
    cycle = 0
    while True:
        started = time.monotonic()
        try:
            if not one_pass(attempt_adds=(cycle % every == 0)):
                return 1
            cycle += 1
        except KeyboardInterrupt:
            log("Stopped.")
            return 0
        except Exception as exc:
            log(f"[{account.name}] Unexpected error, continuing: {exc}")

        # Sleep only the time left in this interval. Sleeping a full interval
        # AFTER the work makes each cycle take work + interval, so a 60s
        # setting was really running every ~87s and drifting under load.
        try:
            time.sleep(max(0.0, interval - (time.monotonic() - started)))
        except KeyboardInterrupt:
            log("Stopped.")
            return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="FirstCry shortlist deliverability watcher")
    ap.add_argument("--loop", action="store_true",
                    help=f"run forever, checking every "
                         f"{config.BOT2_INTERVAL_SECONDS:g}s")
    ap.add_argument("--reset", action="store_true", help="clear saved state")
    ap.add_argument("--status", action="store_true",
                    help="Telegram a snapshot of what's deliverable right now")
    ap.add_argument("--account", metavar="NAME",
                    help="only this account (default: all of them)")
    args = ap.parse_args()

    accounts = config.load_accounts()
    if args.account:
        accounts = [a for a in accounts if a.name == args.account]
        if not accounts:
            log(f"No account named {args.account!r}. Found: "
                f"{[a.name for a in config.load_accounts()]}")
            return 1

    if not accounts:
        log("No accounts configured.")
        log("Put a session file at session.json, or several in accounts/.")
        log("Create one with:  python import_cookies.py")
        return 1

    if len(accounts) > 1:
        log(f"Accounts: {', '.join(a.name for a in accounts)}")

    if args.status:
        return send_status(accounts)

    if args.reset:
        for account in accounts:
            if account.state_file.exists():
                account.state_file.unlink()
                log(f"[{account.name}] State cleared.")

    if not config.telegram_ready():
        log("WARNING: Telegram not configured - alerts will print here only.")

    # Running several accounts in one loop would make each wait on the
    # others. run_all.py gives each its own thread; here we keep it simple
    # and run them in turn, which is fine for a one-shot check.
    if not args.loop:
        return max(watch(a, loop=False) for a in accounts)

    if len(accounts) == 1:
        return watch(accounts[0], loop=True)

    import threading
    threads = [threading.Thread(target=watch, args=(a, True),
                                name=a.name, daemon=True) for a in accounts]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
