"""Parse supported Telegram message links; never resolve invite links."""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class MessageLink:
    chat: str | int
    message_id: int
    private: bool


def parse_message_link(value: str) -> MessageLink | None:
    try:
        url = urlsplit(value.strip())
        if url.scheme != "https" or (url.hostname or "").lower() not in {
            "t.me", "www.t.me", "telegram.me", "www.telegram.me"
        } or url.username or url.password or url.port not in (None, 443):
            return None
        parts = [p for p in url.path.split("/") if p]
        if len(parts) in (3, 4) and parts[0] == "c":
            # Topic links can include a topic/thread ID before the actual message ID.
            if not all(x.isdecimal() and int(x) > 0 for x in parts[1:]):
                return None
            return MessageLink(chat=-int("100" + parts[1]), message_id=int(parts[-1]), private=True)
        if len(parts) == 3 and parts[0] == "s":
            parts = parts[1:]
        if len(parts) == 2 and re.fullmatch(r"[A-Za-z0-9_]{5,32}", parts[0]):
            if parts[0].lower() in ("joinchat", "addstickers"):
                return None
            if parts[1].isdecimal() and int(parts[1]) > 0:
                return MessageLink(chat=parts[0], message_id=int(parts[1]), private=False)
    except (ValueError, OverflowError):
        return None
    return None