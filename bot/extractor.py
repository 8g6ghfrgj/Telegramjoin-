# bot/extractor.py
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

from bot.config import API_ID, API_HASH, EXTRACT_MESSAGES_LIMIT
from bot.utils import extract_telegram_links, normalize_tme_link

logger = logging.getLogger(__name__)

async def extract_links_from_channel(session_string: str, channel_link: str) -> list[str]:
    """
    Extract telegram links from ALL messages in the channel:
    - if EXTRACT_MESSAGES_LIMIT=0: from first message to last message
    - else: last N messages
    """
    channel_link = normalize_tme_link(channel_link)

    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()

    try:
        entity = await client.get_entity(channel_link)

        found = set()

        if EXTRACT_MESSAGES_LIMIT and EXTRACT_MESSAGES_LIMIT > 0:
            # last N messages only (fast mode)
            async for msg in client.iter_messages(entity, limit=EXTRACT_MESSAGES_LIMIT):
                if msg and msg.message:
                    for link in extract_telegram_links(msg.message):
                        found.add(normalize_tme_link(link))
        else:
            # FULL extraction from first to last
            async for msg in client.iter_messages(entity, reverse=True):
                if msg and msg.message:
                    for link in extract_telegram_links(msg.message):
                        found.add(normalize_tme_link(link))

        return sorted(found)

    finally:
        await client.disconnect()
