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
    - else: last N messages only

    IMPORTANT:
    - We normalize all extracted links to unified format:
      https://t.me/<path>
    - Also normalize channel_link itself.
    """
    channel_link = normalize_tme_link(channel_link)

    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()

    try:
        entity = await client.get_entity(channel_link)

        found = set()

        # Fast mode: last N messages only
        if EXTRACT_MESSAGES_LIMIT and EXTRACT_MESSAGES_LIMIT > 0:
            async for msg in client.iter_messages(entity, limit=EXTRACT_MESSAGES_LIMIT):
                if not msg:
                    continue

                text = msg.message or ""
                if not text:
                    continue

                for link in extract_telegram_links(text):
                    found.add(normalize_tme_link(link))

        # Full mode: extract from first message to last message
        else:
            async for msg in client.iter_messages(entity, reverse=True):
                if not msg:
                    continue

                text = msg.message or ""
                if not text:
                    continue

                for link in extract_telegram_links(text):
                    found.add(normalize_tme_link(link))

        return sorted(found)

    finally:
        await client.disconnect()
