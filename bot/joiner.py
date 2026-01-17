# bot/joiner.py
import asyncio
import logging
from typing import Optional, Tuple

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


# ---------------- Dead link errors classification ----------------
DEAD_LINK_EXCEPTIONS = (
    # invite issues
    errors.InviteHashExpiredError,
    errors.InviteHashInvalidError,

    # username/channel issues
    errors.UsernameInvalidError,
    errors.UsernameNotOccupiedError,

    # privacy / permission issues
    errors.ChannelPrivateError,
    errors.ChatAdminRequiredError,

    # other: entity not found
    errors.EntityIdInvalidError,
)


def _is_dead_link_error(e: Exception) -> bool:
    """
    Determine whether an exception means the link is dead/invalid/expired/private.
    """
    return isinstance(e, DEAD_LINK_EXCEPTIONS)


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
        invite = await client(CheckChatlistInviteRequest(value))

        peers = []
        if hasattr(invite, "peers") and invite.peers:
            peers = invite.peers

        if not peers:
            # ممكن يكون المجلد فارغ أو تمت إضافته مسبقاً
            raise Exception("Chat folder invite returned empty peers list")

        await client(JoinChatlistInviteRequest(slug=value, peers=peers))
        return

    raise Exception(f"Unsupported link kind: {kind}")


async def _replace_dead_link_immediately(session_id: int, dead_link_id: int, dead_link: str, reason: str) -> Optional[Tuple[int, str]]:
    """
    Marks link as dead + replaces it with a new link from reserve, assigned to same session.
    Returns (new_link_id, new_link) or None if reserve empty.
    """
    # log as failed for audit, but do not sleep
    db.log_join(session_id, dead_link, "failed", f"dead_link: {reason}")

    # Replace in DB immediately
    replacement = db.replace_dead_assignment(session_id, dead_link_id, dead_reason=reason)

    if not replacement:
        logger.warning(
            f"[Session {session_id}] Dead link detected but reserve empty. "
            f"dead_link={dead_link}"
        )
        return None

    new_link_id, new_link = replacement
    logger.info(
        f"[Session {session_id}] Dead link replaced immediately. "
        f"old={dead_link} -> new={new_link}"
    )
    return (new_link_id, new_link)


async def run_session_joiner(session_id: int, session_string: str, limit: int = 1000, stop_flag=None):
    """
    For each Session:
    - get up to 1000 pending ACTIVE links assigned to it
    - join them sequentially
    - Delay policy:
        * if join success / already participant => sleep JOIN_DELAY_SECONDS (90 default)
        * if dead link => replace immediately without sleep
        * if FloodWait => sleep e.seconds + 5 for THIS SESSION only, then retry
    """
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()

    try:
        pending = db.get_pending_links_for_session(session_id, limit=limit)

        success = 0
        failed = 0

        i = 0
        while i < len(pending):
            link_id, link = pending[i]

            if stop_flag and stop_flag.is_set():
                logger.info(f"[Session {session_id}] Stop flag set. Exiting.")
                break

            try:
                await join_one_link(client, link)

                # If join works => success
                db.mark_join_success(session_id, link_id)
                db.log_join(session_id, link, "success", "")
                success += 1

                logger.info(f"[Session {session_id}] Joined OK: {link}")

                # ✅ Delay ONLY for active successful links
                await asyncio.sleep(JOIN_DELAY_SECONDS)
                i += 1
                continue

            except errors.UserAlreadyParticipantError:
                # considered success
                db.mark_join_success(session_id, link_id)
                db.log_join(session_id, link, "success", "already_participant")
                success += 1

                logger.info(f"[Session {session_id}] Already participant: {link}")

                # ✅ Delay ONLY for active successful links
                await asyncio.sleep(JOIN_DELAY_SECONDS)
                i += 1
                continue

            except errors.FloodWaitError as e:
                # ✅ FloodWait: this session only sleeps specified time, then retries
                wait_s = int(e.seconds) + 5

                # DO NOT mark failed permanently
                db.bump_attempt(session_id, link_id, f"FloodWaitError: {e.seconds}s")
                db.log_join(session_id, link, "failed", f"FloodWaitError wait {wait_s}s")

                logger.warning(
                    f"[Session {session_id}] FloodWait {e.seconds}s -> sleeping {wait_s}s and retrying"
                )
                await asyncio.sleep(wait_s)

                # retry SAME link (no increment i)
                continue

            except Exception as e:
                err = str(e)

                # 1) If dead link -> replace immediately from reserve
                if _is_dead_link_error(e):
                    replacement = await _replace_dead_link_immediately(
                        session_id=session_id,
                        dead_link_id=link_id,
                        dead_link=link,
                        reason=err
                    )

                    # no reserve? mark assignment failed and move on
                    if not replacement:
                        db.mark_join_failed(session_id, link_id, f"dead_no_reserve: {err}")
                        failed += 1
                        i += 1
                        continue

                    # Replace current pending item in-memory, retry immediately without delay
                    new_link_id, new_link = replacement
                    pending[i] = (new_link_id, new_link)
                    continue

                # 2) Non-dead normal error -> failed
                db.mark_join_failed(session_id, link_id, err)
                db.log_join(session_id, link, "failed", err)
                failed += 1

                logger.error(f"[Session {session_id}] Failed join: {link} | Error: {err}")

                # move on without sleeping (error shouldn't waste time)
                i += 1
                continue

        return {"session_id": session_id, "success": success, "failed": failed}

    finally:
        await client.disconnect()
