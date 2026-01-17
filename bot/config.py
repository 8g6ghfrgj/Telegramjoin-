# bot/config.py
import os

# Required Telegram API credentials
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ---------------- Settings ----------------

# Delay between joins for ACTIVE/VALID links only
# Default changed from 60 -> 90 to reduce FloodWait probability
JOIN_DELAY_SECONDS = int(os.getenv("JOIN_DELAY_SECONDS", "90"))

# Link reserve pool:
# Always keep at least this many active, unassigned links in DB as backup
# used for immediate replacement of dead/expired links.
RESERVE_LINKS = int(os.getenv("RESERVE_LINKS", "500"))

# Messages extraction limit:
# 0 = extract all messages from first to last
# >0 = extract last N messages only
EXTRACT_MESSAGES_LIMIT = int(os.getenv("EXTRACT_MESSAGES_LIMIT", "0"))

# Database path
DB_PATH = os.getenv("DB_PATH", "data/sessions.db")

# Safety checks
if API_ID == 0 or not API_HASH or not BOT_TOKEN or OWNER_ID == 0:
    raise RuntimeError(
        "Missing required env vars: API_ID, API_HASH, BOT_TOKEN, OWNER_ID"
    )

# Validate numeric settings
if JOIN_DELAY_SECONDS < 0:
    raise RuntimeError("JOIN_DELAY_SECONDS must be >= 0")

if RESERVE_LINKS < 0:
    raise RuntimeError("RESERVE_LINKS must be >= 0")

if EXTRACT_MESSAGES_LIMIT < 0:
    raise RuntimeError("EXTRACT_MESSAGES_LIMIT must be >= 0")
