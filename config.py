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
