# bot/joiner.py
import asyncio
import logging
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from bot.config import API_ID, API_HASH, JOIN_DELAY_SECONDS
from bot.utils import parse_invite_or_username
from bot import db

logger = logging.getLogger(__name__)

async def join_one_link(client: TelegramClient, link: str) -> None:
    kind, value = parse_invite_or_username(link)

    if kind == "invite":
        await client(ImportChatInviteRequest(value))
    else:
        await client(JoinChannelRequest(value))

async def run_session_joiner(session_id: int, session_string: str, limit: int = 1000, stop_flag=None):
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()

    try:
        pending = db.get_pending_links_for_session(session_id, limit=limit)

        success = 0
        failed = 0

        for link_id, link in pending:
            if stop_flag and stop_flag.is_set():
                break

            try:
                await join_one_link(client, link)
                db.mark_join_success(session_id, link_id)
                db.log_join(session_id, link, "success", "")
                success += 1

            except errors.UserAlreadyParticipantError:
                # يعتبر نجاح (عضو مسبقاً)
                db.mark_join_success(session_id, link_id)
                db.log_join(session_id, link, "success", "already_participant")
                success += 1

            except errors.FloodWaitError as e:
                # احترام flood wait
                wait_s = int(e.seconds) + 5
                db.mark_join_failed(session_id, link_id, f"FloodWaitError: {e.seconds}s")
                db.log_join(session_id, link, "failed", f"FloodWaitError: wait {wait_s}s")
                failed += 1
                await asyncio.sleep(wait_s)

            except Exception as e:
                err = str(e)
                db.mark_join_failed(session_id, link_id, err)
                db.log_join(session_id, link, "failed", err)
                failed += 1

            # Sleep between links
            await asyncio.sleep(JOIN_DELAY_SECONDS)

        return {"session_id": session_id, "success": success, "failed": failed}

    finally:
        await client.disconnect()
