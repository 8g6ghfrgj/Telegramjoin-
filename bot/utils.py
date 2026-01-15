# bot/utils.py
import re
from urllib.parse import urlparse

# Telegram link extractor:
# - username links:  https://t.me/SomeChannel
# - invite links:    https://t.me/+HASH
# - old invite:      https://t.me/joinchat/HASH
# - folder invite:   https://t.me/addlist/SLUG
TG_LINK_RE = re.compile(
    r"(https?://t\.me/(?:addlist/|joinchat/|\+)?[A-Za-z0-9_\-+]+)",
    re.IGNORECASE
)


def extract_telegram_links(text: str) -> list[str]:
    """Extract all telegram links from any text (dedup is done elsewhere)."""
    if not text:
        return []

    links = TG_LINK_RE.findall(text)

    cleaned: list[str] = []
    for l in links:
        # remove trailing punctuation
        l = l.strip().rstrip(").,;!؟…]}>")
        cleaned.append(l)

    return cleaned


def normalize_tme_link(link: str) -> str:
    """Normalize t.me links (remove query params, normalize host/path)."""
    link = (link or "").strip()

    try:
        u = urlparse(link)
        if u.netloc.lower() in ("t.me", "telegram.me"):
            path = u.path.strip("/")
            return f"https://t.me/{path}"
    except Exception:
        pass

    return link


def parse_link_type(link: str) -> tuple[str, str]:
    """
    Detect link type.

    Returns:
      ("folder", slug)    for https://t.me/addlist/<slug>
      ("invite", hash)    for https://t.me/+HASH or https://t.me/joinchat/HASH
      ("username", name)  for https://t.me/<username>
    """
    link = normalize_tme_link(link)

    if "t.me/addlist/" in link:
        slug = link.split("t.me/addlist/")[-1].strip("/")
        return ("folder", slug)

    if "t.me/+" in link:
        invite_hash = link.split("t.me/+")[-1].strip("/")
        return ("invite", invite_hash)

    if "t.me/joinchat/" in link:
        invite_hash = link.split("t.me/joinchat/")[-1].strip("/")
        return ("invite", invite_hash)

    username = link.split("t.me/")[-1].strip("/")
    return ("username", username)
