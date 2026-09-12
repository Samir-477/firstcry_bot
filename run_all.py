"""Run both bots together, from one command.

    python run_all.py

Bot 1 checks for newly added Hot Wheels once a day.
Bot 2 checks whether your shortlist items can reach your pincode, every
60 seconds, and puts any that can into your cart.

Each runs on its own thread, so a slow or failing check in one never holds up
the other. Ctrl+C stops both cleanly.
"""
import sys
import threading
import time
from datetime import datetime

import requests

import bot1_new_arrivals as bot1
import bot2_wishlist as bot2
import config
import firstcry_account as fa
import notifier

stop = threading.Event()


def log(tag: str, msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] [{tag}] {msg}", flush=True)


def wait(seconds: float) -> bool:
    """Sleep, but wake immediately on shutdown. False means time to stop."""
    return not stop.wait(seconds)


# --------------------------------------------------------------------------
# Bot 1 - new arrivals, once a day
# --------------------------------------------------------------------------

def run_bot1() -> None:
    interval = config.BOT1_INTERVAL_HOURS * 3600
    log("BOT1", f"Watching for new Hot Wheels every "
                f"{config.BOT1_INTERVAL_HOURS:g}h")
    while not stop.is_set():
        started = time.monotonic()
        try:
            found = bot1.check_once()
            if found:
                log("BOT1", f"{found} change(s) reported")
        except requests.RequestException as exc:
            log("BOT1", f"network problem, retrying next cycle: {exc}")
        except Exception as exc:
            log("BOT1", f"unexpected error, continuing: {exc}")
        if not wait(max(0.0, interval - (time.monotonic() - started))):
            return


# --------------------------------------------------------------------------
# Bot 2 - shortlist deliverability, every minute
# --------------------------------------------------------------------------

def run_bot2(account: config.Account) -> None:
    tag = f"BOT2:{account.name}" if account.name != "default" else "BOT2"
    interval = config.BOT2_INTERVAL_SECONDS
    log(tag, f"Watching shortlist deliverability every {interval:g}s "
             f"(pincode {account.pincode})")
    state = bot2.load_state(account)
    quiet_since = None

    # A single failed read is not proof the session is dead - FirstCry serves
    # the odd error page, and those look identical to being logged out. Only
    # declare expiry after several in a row, and never give up entirely: if
    # a fresh session.json is dropped in, the bot should heal on its own.
    consecutive_failures = 0
    expiry_reported = False
    FAILURES_BEFORE_ALERT = 3
    RETRY_WHEN_EXPIRED = 300.0

    while not stop.is_set():
        started = time.monotonic()
        try:
            items, alerts = bot2.check_once(account, state)
            state = {"items": items}
            bot2.save_state(account, items)

            if expiry_reported:
                log(tag, "session is working again - back to normal")
                notifier.send(f"✅ <b>FirstCry session restored"
                              f"{notifier._who(account.name)}</b>\n\n"
                              "Bot 2 is watching this cart again.")
            consecutive_failures = 0
            expiry_reported = False

            # Only log every cycle when something happened; otherwise a short
            # heartbeat every 30 minutes so the terminal stays readable.
            now = time.time()
            if alerts:
                quiet_since = now
            elif quiet_since is None or now - quiet_since >= 1800:
                quiet_since = now
                deliverable = sum(1 for v in items.values()
                                  if v.get("deliverable"))
                log(tag, f"still watching - {len(items)} on shortlist, "
                         f"{deliverable} deliverable to {account.pincode}")

        except fa.SessionExpired as exc:
            consecutive_failures += 1
            if consecutive_failures < FAILURES_BEFORE_ALERT:
                log(tag, f"session read failed ({consecutive_failures}/"
                            f"{FAILURES_BEFORE_ALERT}) - could be a blip: {exc}")
            elif not expiry_reported:
                log(tag, f"SESSION EXPIRED after {consecutive_failures} "
                            f"failed checks: {exc}")
                log(tag, "Fix with: python import_cookies.py")
                log(tag, f"Still retrying every {RETRY_WHEN_EXPIRED:.0f}s - "
                            f"drop in a new session.json and it resumes itself.")
                notifier.send_session_expired(account.name)
                expiry_reported = True
        except requests.RequestException as exc:
            log(tag, f"network problem, retrying: {exc}")
        except Exception as exc:
            log(tag, f"unexpected error, continuing: {exc}")

        # Sleep only what's left of the interval - the checks themselves take
        # a couple of seconds, so sleeping a full interval afterwards made a
        # 60s setting run every ~87s. Back right off while expired: there is
        # no point hammering a dead session every few seconds.
        gap = RETRY_WHEN_EXPIRED if expiry_reported else interval
        if not wait(max(0.0, gap - (time.monotonic() - started))):
            return


# --------------------------------------------------------------------------

def main() -> int:
    print("=" * 62)
    print(" FIRSTCRY HOT WHEELS BOTS")
    print("=" * 62)
    print(f"  Pincode      : {config.PINCODE}")
    print(f"  Bot 1        : new listings, every {config.BOT1_INTERVAL_HOURS:g}h")
    _accounts = config.load_accounts()
    print(f"  Bot 2        : shortlist deliverability, every "
          f"{config.BOT2_INTERVAL_SECONDS:g}s")
    print(f"  Accounts     : "
          + (", ".join(a.name for a in _accounts) if _accounts else "NONE"))
    print(f"  Auto-add     : {'on' if config.AUTO_ADD_TO_CART else 'off'}")
    print(f"  Telegram     : {'connected' if config.telegram_ready() else 'NOT SET UP'}")
    print("=" * 62)
    print("  Ctrl+C to stop")
    print("=" * 62 + "\n")

    if not config.telegram_ready():
        log("SETUP", "Telegram isn't configured - alerts will print here only.")
        log("SETUP", "Fix with: python setup_telegram.py")

    threads = [threading.Thread(target=run_bot1, name="bot1", daemon=True)]

    if not _accounts:
        log("SETUP", "No account session found - Bot 2 cannot run.")
        log("SETUP", "Fix with: python import_cookies.py")
        log("SETUP", "Starting Bot 1 only.\n")
    else:
        # One thread per account, so a slow or dead account never holds up
        # the others.
        for account in _accounts:
            threads.append(threading.Thread(
                target=run_bot2, args=(account,),
                name=f"bot2-{account.name}", daemon=True))

    for t in threads:
        t.start()

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        log("MAIN", "stopping both bots...")
        stop.set()
        for t in threads:
            t.join(timeout=5)
        log("MAIN", "stopped.")
        return 0

    log("MAIN", "all watchers have exited.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
