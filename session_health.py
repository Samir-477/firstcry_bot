"""Track how long FirstCry sessions actually last.

FirstCry's FC_AUTH cookie is opaque and is never re-issued - its lifetime is
fixed at login and nothing in the file says when it ends. Verified by
inspecting Set-Cookie on every endpoint the bots touch: laravel_session and
the cart cookie get refreshed, FC_AUTH never does.

So instead of predicting, we measure. Each time a session dies we record how
long it lasted. After the first cycle you know roughly what to expect, and
the bot can warn you before the next one runs out.
"""
import json
import time
from datetime import datetime

import config

HISTORY_FILE = config.STATE_DIR / "session_history.json"

# Until we have measured a real lifetime, assume nothing and stay quiet.
# Once we know, warn when a session reaches this fraction of its expected life.
WARN_AT_FRACTION = 0.8


def _load() -> dict:
    if not HISTORY_FILE.exists():
        return {}
    try:
        with open(HISTORY_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def age_days(account: config.Account) -> float:
    """How long since this session file was written."""
    if not account.session_file.exists():
        return 0.0
    return (time.time() - account.session_file.stat().st_mtime) / 86400


def record_death(account: config.Account) -> float | None:
    """Note that this session just expired. Returns the lifetime in days.

    Recorded once per session file: if the bot keeps retrying a dead
    session we do not want dozens of entries for the same death.
    """
    data = _load()
    entry = data.setdefault(account.name, {"lifetimes": [], "last_death_at": None})

    lived = age_days(account)
    stamp = datetime.now().isoformat(timespec="seconds")

    # Same dead file as last time? Don't record it twice.
    if entry.get("last_death_file_mtime") == account.session_file.stat().st_mtime:
        return None

    entry["lifetimes"].append(round(lived, 2))
    entry["lifetimes"] = entry["lifetimes"][-10:]   # keep the last ten
    entry["last_death_at"] = stamp
    entry["last_death_file_mtime"] = account.session_file.stat().st_mtime
    _save(data)
    return lived


def expected_lifetime(account: config.Account) -> float | None:
    """Average observed lifetime, or None if we have never seen one die."""
    lifetimes = _load().get(account.name, {}).get("lifetimes") or []
    return sum(lifetimes) / len(lifetimes) if lifetimes else None


def status(account: config.Account) -> str:
    """One human line about this session's age and prospects."""
    age = age_days(account)
    expected = expected_lifetime(account)
    if expected is None:
        return (f"session is {age:.1f} days old "
                f"(lifetime not measured yet - the first expiry will tell us)")
    left = expected - age
    if left <= 0:
        return (f"session is {age:.1f} days old, past the usual "
                f"{expected:.1f} days - could go at any time")
    return (f"session is {age:.1f} days old, usually lasts "
            f"{expected:.1f} - about {left:.1f} days left")


def should_warn(account: config.Account) -> bool:
    """True when the session is near the end of its usual life."""
    expected = expected_lifetime(account)
    if expected is None:
        return False
    return age_days(account) >= expected * WARN_AT_FRACTION


if __name__ == "__main__":
    accounts = config.load_accounts()
    if not accounts:
        print("No accounts configured.")
    for a in accounts:
        print(f"{a.name:<8} {status(a)}")
