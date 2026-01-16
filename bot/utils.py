# bot/utils.py
import re
from urllib.parse import urlparse

# Telegram link extractor:
# Supports:
# - username links:   https://t.me/SomeChannel   OR  t.me/SomeChannel
# - invite links:     https://t.me/+HASH         OR  t.me/+HASH
# - old invite links: https://t.me/joinchat/HASH OR  t.me/joinchat/HASH
# - folder invite:    https://t.me/addlist/SLUG  OR  t.me/addlist/SLUG
TG_LINK_RE = re.compile(
    r"((?:https?://)?t\.me/(?:addlist/|joinchat/|\+)?[A-Za-z0-9_\-+]+)",
    re.IGNORECASE
)


def extract_telegram_links(text: str) -> list[str]:
    """Extract all Telegram links from any text."""
    if not text:
        return []

    links = TG_LINK_RE.findall(text)

    cleaned: list[str] = []
    for l in links:
        l = l.strip()

        # remove trailing punctuation / brackets (common in formatted messages)
        l = l.rstrip(").,;!؟…]}>\"'")

        cleaned.append(l)

    return cleaned


def normalize_tme_link(link: str) -> str:
    """
    Normalize Telegram links:
    - force https scheme
    - remove query parameters
    - normalize to 'https://t.me/<path>'
    """
    link = (link or "").strip()

    # Add scheme if missing
    if link.startswith("t.me/"):
        link = "https://" + link

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
