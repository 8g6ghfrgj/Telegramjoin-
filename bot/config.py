# bot/config.py
import os

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Settings
JOIN_DELAY_SECONDS = int(os.getenv("JOIN_DELAY_SECONDS", "60"))
EXTRACT_MESSAGES_LIMIT = int(os.getenv("EXTRACT_MESSAGES_LIMIT", "0"))
# EXTRACT_MESSAGES_LIMIT:
# 0 = extract all messages from first to last
# if > 0: extract last N messages only

DB_PATH = os.getenv("DB_PATH", "data/sessions.db")

if API_ID == 0 or not API_HASH or not BOT_TOKEN or OWNER_ID == 0:
    raise RuntimeError("Missing required env vars: API_ID, API_HASH, BOT_TOKEN, OWNER_ID")
