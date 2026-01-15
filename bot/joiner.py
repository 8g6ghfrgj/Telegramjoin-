# bot/joiner.py
import asyncio
import logging

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

# دعم روابط المجلدات addlist
from telethon.tl.functions.chatlists import (
    CheckChatlistInviteRequest,
    JoinChatlistInviteRequest
)

from bot.config import API_ID, API_HASH, JOIN_DELAY_SECONDS
from bot.utils import parse_link_type
from bot import db

logger = logging.getLogger(__name__)


async def join_one_link(client: TelegramClient, link: str) -> None:
    """
    Join:
    - username links (public)
    - invite links (+hash / joinchat/hash)
    - chat folder links (addlist/slug)
    """
    kind, value = parse_link_type(link)

    # 1) Invite hash links
    if kind == "invite":
        await client(ImportChatInviteRequest(value))
        return

    # 2) Public username links
    if kind == "username":
        await client(JoinChannelRequest(value))
        return

    # 3) Folder links: https://t.me/addlist/<slug>
    if kind == "folder":
        # 1) check invite to get the peers list
        invite = await client(CheckChatlistInviteRequest(value))

        peers = []
        if hasattr(invite, "peers") and invite.peers:
            peers = invite.peers

        if not peers:
            # ممكن يكون المجلد فارغ أو تمت إضافته مسبقاً
            raise Exception("Chat folder invite returned empty peers list")

        # 2) join all peers in this folder
        await client(JoinChatlistInviteRequest(slug=value, peers=peers))
        return

    raise Exception(f"Unsupported link kind: {kind}")


async def run_session_joiner(session_id: int, session_string: str, limit: int = 1000, stop_flag=None):
    """
    For each Session:
    - get up to 1000 pending links assigned to it
    - join them sequentially with JOIN_DELAY_SECONDS
    """
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()

    try:
        pending = db.get_pending_links_for_session(session_id, limit=limit)

        success = 0
        failed = 0

        for link_id, link in pending:
            if stop_flag and stop_flag.is_set():
                logger.info("Stop flag set. Exiting session joiner.")
                break

            try:
                await join_one_link(client, link)

                db.mark_join_success(session_id, link_id)
                db.log_join(session_id, link, "success", "")
                success += 1

                logger.info(f"[Session {session_id}] Joined OK: {link}")

            except errors.UserAlreadyParticipantError:
                # يعتبر نجاح
                db.mark_join_success(session_id, link_id)
                db.log_join(session_id, link, "success", "already_participant")
                success += 1

                logger.info(f"[Session {session_id}] Already participant: {link}")

            except errors.FloodWaitError as e:
                # احترام floodwait
                wait_s = int(e.seconds) + 5

                db.mark_join_failed(session_id, link_id, f"FloodWaitError: {e.seconds}s")
                db.log_join(session_id, link, "failed", f"FloodWaitError wait {wait_s}s")
                failed += 1

                logger.warning(f"[Session {session_id}] FloodWait {e.seconds}s -> sleeping {wait_s}s")
                await asyncio.sleep(wait_s)

            except Exception as e:
                err = str(e)

                db.mark_join_failed(session_id, link_id, err)
                db.log_join(session_id, link, "failed", err)
                failed += 1

                logger.error(f"[Session {session_id}] Failed join: {link} | Error: {err}")

            # Sleep between each link (policy = 60s)
            await asyncio.sleep(JOIN_DELAY_SECONDS)

        return {"session_id": session_id, "success": success, "failed": failed}

    finally:
        await client.disconnect()
