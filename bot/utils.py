# bot/utils.py
import re
from urllib.parse import urlparse

TG_LINK_RE = re.compile(
    r"(https?://t\.me/(?:\+|joinchat/)?[A-Za-z0-9_\-+]+)",
    re.IGNORECASE
)

def extract_telegram_links(text: str) -> list[str]:
    if not text:
        return []
    links = TG_LINK_RE.findall(text)
    # normalize remove trailing punctuation
    cleaned = []
    for l in links:
        l = l.strip().rstrip(").,;!؟…]")
        cleaned.append(l)
    return cleaned

def normalize_tme_link(link: str) -> str:
    link = link.strip()
    # remove tracking params if exist
    try:
        u = urlparse(link)
        if u.netloc.lower() in ("t.me", "telegram.me"):
            path = u.path.strip("/")
            if u.query:
                # just drop query, keep base path
                return f"https://t.me/{path}"
    except Exception:
        pass
    return link

def parse_invite_or_username(link: str) -> tuple[str, str]:
    """
    Returns: ("invite", hash) or ("username", username)
    Supports:
      https://t.me/+HASH
      https://t.me/joinchat/HASH
      https://t.me/username
    """
    link = normalize_tme_link(link)

    if "t.me/+" in link:
        return ("invite", link.split("t.me/+")[-1].strip("/"))

    if "t.me/joinchat/" in link:
        return ("invite", link.split("t.me/joinchat/")[-1].strip("/"))

    # username
    username = link.split("t.me/")[-1].strip("/")
    return ("username", username)
