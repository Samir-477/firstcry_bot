"""Central settings. Everything tweakable lives in .env, not in code."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
# Accepts one ID, or several separated by commas:
#   TELEGRAM_CHAT_ID=12345678
#   TELEGRAM_CHAT_ID=12345678,-1009876543210,87654321
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_CHAT_IDS = [c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()]

PINCODE = os.getenv("PINCODE", "560075").strip()
BRAND_ID = os.getenv("BRAND_ID", "113").strip()  # 113 = Hot Wheels

BOT1_INTERVAL_HOURS = float(os.getenv("BOT1_INTERVAL_HOURS", "24"))
BOT2_INTERVAL_SECONDS = float(os.getenv("BOT2_INTERVAL_SECONDS", "60"))

# When a wishlist item comes back in stock, should Bot 2 put it in your
# cart automatically? It never buys - it only adds.
AUTO_ADD_TO_CART = os.getenv("AUTO_ADD_TO_CART", "true").strip().lower() in (
    "1", "true", "yes", "on")

# Deliverability is checked every cycle, but pushing shortlist items into
# the cart is retried less often - out-of-stock items would otherwise be
# re-attempted every single minute for nothing.
ADD_TO_CART_EVERY_N_CHECKS = int(os.getenv("ADD_TO_CART_EVERY_N_CHECKS", "5"))

STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)

SEEN_PRODUCTS_FILE = STATE_DIR / "seen_products.json"
WISHLIST_STATE_FILE = STATE_DIR / "wishlist_state.json"
SESSION_FILE = ROOT / "session.json"


def telegram_ready() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS
                and not TELEGRAM_BOT_TOKEN.startswith("123456789:"))


# --------------------------------------------------------------------------
# Accounts - Bot 2 can watch more than one FirstCry login
# --------------------------------------------------------------------------
# Drop a session file per account into accounts/ :
#
#     accounts/samir.json
#     accounts/priya.json
#
# The filename becomes the account's name, shown on every alert. Each gets
# its own state file, so their baselines never mix.
#
# Deliverability comes from each account's own cart, which uses whatever
# delivery address that account has set on FirstCry - so two accounts in
# different cities just work, with no extra configuration.
#
# To override the pincode used for an account's shortlist lookup, set
# PINCODE_<NAME> in .env (e.g. PINCODE_PRIYA=400001).
#
# If accounts/ is empty or missing, the old single session.json is used.

ACCOUNTS_DIR = ROOT / "accounts"


class Account:
    """One FirstCry login the bot watches."""

    def __init__(self, name: str, session_file: Path, state_file: Path,
                 pincode: str):
        self.name = name
        self.session_file = session_file
        self.state_file = state_file
        self.pincode = pincode

    def __repr__(self) -> str:
        return f"<Account {self.name} pincode={self.pincode}>"


def load_accounts() -> list[Account]:
    """Every account to watch, newest config style first."""
    accounts: list[Account] = []

    if ACCOUNTS_DIR.is_dir():
        for path in sorted(ACCOUNTS_DIR.glob("*.json")):
            name = path.stem
            accounts.append(Account(
                name=name,
                session_file=path,
                state_file=STATE_DIR / f"wishlist_{name}.json",
                pincode=os.getenv(f"PINCODE_{name.upper()}", PINCODE).strip(),
            ))

    # Fall back to the original single-account layout.
    if not accounts and SESSION_FILE.exists():
        accounts.append(Account(name="default",
                                session_file=SESSION_FILE,
                                state_file=WISHLIST_STATE_FILE,
                                pincode=PINCODE))
    return accounts
