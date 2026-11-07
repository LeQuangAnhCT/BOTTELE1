"""Private Telegram music helper: Jamendo, direct audio URLs, Telegram message links."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.resolver import DefaultResolver
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)
from telethon import TelegramClient, utils

from links import parse_message_link

load_dotenv()
LOG = logging.getLogger(__name__)
MAX_UPLOAD = 48 * 1024 * 1024
MAX_BOT_DOWNLOAD = 20 * 1024 * 1024
SESSION_PATH = Path("sessions") / "my_telegram"
ALLOWED_SUFFIXES = {".mp3", ".m4a", ".ogg", ".flac", ".wav"}


class DownloadError(Exception):
    """A user-facing error (without secrets)."""


class PublicResolver(DefaultResolver):
    """Reject private/loopback IPs when connecting to untrusted URLs."""

    async def resolve(self, host, port=0, family=0):
        records = await super().resolve(host, port, family)
        if not records:
            raise DownloadError("Không thể phân giải tên miền.")
        for record in records:
            if not ipaddress.ip_address(record["host"]).is_global:
                raise DownloadError("Không cho phép truy cập địa chỉ nội bộ.")
        return records


def validate_http_url(value: str, *, jamendo=False) -> str:
    try:
        url = urlsplit(value)
        hostname = url.hostname
        if url.scheme != "https" or not hostname or url.username or url.password or url.port not in (None, 443):
            raise ValueError
        if ipaddress.ip_address(hostname).is_global is False:
            raise ValueError
    except ValueError:
        # Domain names are not numeric IPs and are checked by PublicResolver.
        try:
            url = urlsplit(value)
            hostname = url.hostname
            if (url.scheme != "https" or not hostname or url.username or url.password
                    or url.port not in (None, 443)):
                raise DownloadError("Chỉ hỗ trợ link HTTPS công khai.")
            if _is_ip_literal(hostname):
                raise DownloadError("Không cho phép địa chỉ IP nội bộ.")
        except ValueError as exc:
            raise DownloadError("Link không hợp lệ.") from exc
    if not jamendo and Path(url.path).suffix.lower() not in (".mp3", ".m4a"):
        raise DownloadError("Link phải trỏ trực tiếp tới file .mp3 hoặc .m4a (không hỗ trợ trang nghe nhạc).")
    return value


def _is_ip_literal(hostname: str) -> bool:
    try:
        return not ipaddress.ip_address(hostname).is_global
    except ValueError:
        return False


async def get_session():
    timeout = aiohttp.ClientTimeout(total=200, connect=20, sock_read=45)
    return aiohttp.ClientSession(
        timeout=timeout, trust_env=False,
        connector=aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False),
    )


async def fetch_file(url: str, dest: Path, *, jamendo=False) -> Path:
    validate_http_url(url, jamendo=jamendo)
    async with await get_session() as session:
        current = url
        # Follow redirects manually to validate every target before connecting.
        for _ in range(5):
            async with session.get(current, allow_redirects=False) as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise DownloadError("Link chuyển hướng không hợp lệ.")
                    current = urljoin(current, location)
                    validate_http_url(current, jamendo=True)
                    continue
                if response.status != 200:
                    raise DownloadError(f"Máy chủ nhạc trả về HTTP {response.status}.")
                if response.content_type in ("text/html", "application/json", "text/plain", "image/jpeg"):
                    raise DownloadError("Đường dẫn không trả về file âm thanh.")
                if int(response.headers.get("Content-Length", "0")) > MAX_UPLOAD:
                    raise DownloadError("File vượt giới hạn 48 MB.")
                received = 0
                with dest.open("wb") as outfile:
                    async for chunk in response.content.iter_chunked(256 * 1024):
                        received += len(chunk)
                        if received > MAX_UPLOAD:
                            raise DownloadError("File vượt giới hạn 48 MB.")
                        outfile.write(chunk)
                if received == 0:
                    raise DownloadError("File âm thanh rỗng.")
                return dest
    raise DownloadError("Link chuyển hướng quá nhiều lần.")


async def search_jamendo(term: str, client_id: str) -> list[dict]:
    if not client_id:
        raise DownloadError("Chưa cấu hình JAMENDO_CLIENT_ID trong .env.")
    async with await get_session() as session:
        params = {
            "client_id": client_id, "format": "json", "limit": 20,
            "search": term, "audiodlformat": "mp32",
        }
        async with session.get("https://api.jamendo.com/v3.0/tracks/", params=params) as response:
            if response.status != 200:
                raise DownloadError("Jamendo hiện không phản hồi.")
            data = await response.json(content_type=None)
    if data.get("headers", {}).get("status") != "success":
        raise DownloadError("Jamendo báo lỗi. Kiểm tra Client ID.")
    return [item for item in data.get("results", [])
            if item.get("audiodownload_allowed") is True
            and item.get("audiodownload") and item.get("license_ccurl")][:6]


async def to_mp3(src: Path, directory: Path) -> Path:
    if src.suffix.lower() == ".mp3":
        return src
    if shutil.which("ffmpeg") is None:
        raise DownloadError("File không phải MP3. Cài FFmpeg và thêm vào PATH để chuyển sang MP3.")
    out = directory / "converted.mp3"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(src), "-vn", "-c:a", "libmp3lame", "-b:a", "160k", str(out),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, errors = await asyncio.wait_for(proc.communicate(), timeout=180)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise DownloadError("Chuyển MP3 quá thời gian cho phép.") from exc
    if proc.returncode != 0 or not out.exists():
        LOG.warning("FFmpeg failed: %s", errors.decode(errors="replace")[:300])
        raise DownloadError("Không thể chuyển file âm thanh sang MP3.")
    if out.stat().st_size > MAX_UPLOAD:
        raise DownloadError("File MP3 sau chuyển đổi vượt 48 MB.")
    return out


async def allowed(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    owner = os.getenv("ALLOWED_USER_ID", "")
    ok = bool(user and chat and chat.type == "private" and owner.isdecimal()
              and int(owner) == user.id)
    if not ok and update.callback_query:
        await update.callback_query.answer("Bot cá nhân: bạn không có quyền sử dụng.", show_alert=True)
    elif not ok and update.message and chat and chat.type == "private":
        await update.message.reply_text("⛔ Bot chỉ phục vụ chủ sở hữu. Dùng /id để xem User ID của bạn.")
    return ok


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text(f"Telegram User ID của bạn: {update.effective_user.id}")


HELP = (
    "🎧 BOT TẢI NHẠC CÁ NHÂN\n\n"
    "• /tim ten bai hat — tìm nhạc trên Jamendo (chỉ bài được phép tải).\n"
    "• /link https://site.com/music.mp3 — tải MP3/M4A trực tiếp.\n"
    "• /link https://t.me/c/123456/789 — lấy nhạc từ tin nhắn Telegram.\n"
    "• Hoặc gửi thẳng tên bài, link, hay chuyển tiếp file nhạc tới bot.\n"
    "• /id — xem Telegram User ID.\n\n"
    "Đường dẫn t.me/c/... chỉ chạy khi tài khoản Telegram đã đăng nhập Telethon "
    "và có quyền xem nhóm/kênh đó. Không hỗ trợ Secret Chats hoặc link chat 1:1 không có message link."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await allowed(update):
        await update.message.reply_text(HELP)


async def send_audio_file(message, context, src: Path, directory: Path, title="Bản nhạc", performer=None, caption=None):
    target = await to_mp3(src, directory)
    if target.stat().st_size > MAX_UPLOAD:
        raise DownloadError("File vượt giới hạn gửi Telegram (48 MB an toàn).")
    with target.open("rb") as handle:
        await context.bot.send_audio(
            chat_id=message.chat_id, audio=handle, filename="music.mp3",
            title=title[:64], performer=(performer or "")[:64] or None,
            caption=(caption or "")[:1024] or None,
            write_timeout=180, read_timeout=180, connect_timeout=30,
        )


async def deliver(message, context, operation):
    status = await message.reply_text("⏳ Đang xử lý nhạc...")
    try:
        with tempfile.TemporaryDirectory(prefix="tele_music_") as td:
            await operation(Path(td))
        await status.edit_text("✅ Đã gửi nhạc.")
    except DownloadError as exc:
        await status.edit_text(f"❌ {exc}")
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
        LOG.warning("Download failed: %s", type(exc).__name__)
        await status.edit_text("❌ Lỗi tải nhạc hoặc kết nối. Kiểm tra link và thử lại.")
    except Exception:
        LOG.exception("Unexpected music delivery failure")
        await status.edit_text("❌ Không xử lý được yêu cầu. Xem log để biết chi tiết.")


async def direct_link(message, context, url):
    async def op(directory):
        suffix = Path(urlsplit(url).path).suffix.lower()
        path = await fetch_file(url, directory / f"source{suffix}")
        await send_audio_file(message, context, path, directory, title="Nhạc từ đường dẫn")
    await deliver(message, context, op)


async def telegram_link(message, context, url):
    ref = parse_message_link(url)
    if ref is None:
        raise DownloadError("Đường dẫn tin nhắn Telegram không hợp lệ.")
    client = context.application.bot_data.get("user_client")
    if client is None or not await client.is_user_authorized():
        await message.reply_text("❌ Chưa đăng nhập Telegram cá nhân. Chạy: python login.py, rồi khởi động lại bot.")
        return

    async def op(directory):
        try:
            if ref.private:
                # Resolve only from conversations the logged-in account actually has.
                dialogs = await client.get_dialogs(limit=None)
                peer = next((d.entity for d in dialogs
                             if utils.get_peer_id(d.entity) == ref.chat), None)
                if peer is None:
                    raise DownloadError("Tài khoản của bạn không có quyền vào nhóm/kênh này.")
            else:
                peer = await client.get_entity(ref.chat)
            item = await client.get_messages(peer, ids=ref.message_id)
        except DownloadError:
            raise
        except Exception as exc:
            LOG.warning("Telegram link fetch error: %s", type(exc).__name__)
            raise DownloadError("Không xem được tin nhắn. Kiểm tra quyền truy cập và link.") from exc
        if not item:
            raise DownloadError("Không tìm thấy tin nhắn đó.")
        if getattr(item, "noforwards", False) or getattr(peer, "noforwards", False):
            raise DownloadError("Tin nhắn được bảo vệ, không hỗ trợ lưu hoặc chuyển tiếp.")
        media_file = item.file
        if not media_file:
            raise DownloadError("Tin nhắn không chứa file âm thanh.")
        ext = Path(media_file.name or "").suffix.lower()
        mime = media_file.mime_type or ""
        if ext not in ALLOWED_SUFFIXES and not mime.startswith("audio/"):
            raise DownloadError("Tin nhắn không chứa nhạc/audio được hỗ trợ.")
        if not media_file.size or media_file.size > MAX_UPLOAD:
            raise DownloadError("Không xác định được dung lượng hoặc file vượt 48 MB.")
        downloaded = await client.download_media(item, file=str(directory / "telegram_audio"))
        if not downloaded:
            raise DownloadError("Không tải được media từ Telegram.")
        path = Path(downloaded)
        if path.stat().st_size > MAX_UPLOAD:
            raise DownloadError("File vượt giới hạn 48 MB.")
        await send_audio_file(message, context, path, directory,
                              title=Path(media_file.name or "Bản nhạc").stem)
    await deliver(message, context, op)


async def find_music(message, context, term):
    if len(term) > 120:
        await message.reply_text("Tên bài hát quá dài (tối đa 120 ký tự).")
        return
    try:
        tracks = await search_jamendo(term, os.getenv("JAMENDO_CLIENT_ID", ""))
    except (DownloadError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
        await message.reply_text(f"❌ Không thể tìm nhạc: {exc if isinstance(exc, DownloadError) else 'lỗi kết nối'}")
        return
    if not tracks:
        await message.reply_text("Không tìm thấy bài được phép tải trên Jamendo. Thử từ khóa khác nhé.")
        return
    context.user_data["tracks"] = tracks
    keys = [[InlineKeyboardButton(
        f"🎵 {t.get('name', 'Nhạc')[:32]} — {t.get('artist_name', '')[:22]}",
        callback_data=f"track:{i}")]
        for i, t in enumerate(tracks)]
    await message.reply_text("Chọn bài để nhận MP3:", reply_markup=InlineKeyboardMarkup(keys))


async def chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    q = update.callback_query
    await q.answer()
    try:
        index = int(q.data.removeprefix("track:"))
        song = context.user_data.get("tracks", [])[index]
        if index < 0 or not song.get("audiodownload_allowed"):
            raise (IndexError())
    except (IndexError, ValueError, AttributeError):
        await q.message.reply_text("Kết quả đã hết hạn. Hãy tìm bài lại.")
        return

    async def op(directory):
        path = await fetch_file(song["audiodownload"], directory / "jamendo.mp3", jamendo=True)
        await send_audio_file(q.message, context, path, directory,
                              title=song.get("name", "Bản nhạc"),
                              performer=song.get("artist_name"),
                              caption=f"Nguồn: Jamendo\nGiấy phép: {song.get('license_ccurl', '')}")
    await deliver(q.message, context, op)


async def parse_request(message, context, raw):
    raw = raw.strip()
    if not raw:
        await message.reply_text(HELP)
        return
    if raw.startswith("https://"):
        if parse_message_link(raw):
            await telegram_link(message, context, raw)
        elif (urlsplit(raw).hostname or "").lower() in ("t.me", "www.t.me", "telegram.me"):
            await message.reply_text("❌ Đây không phải link tin nhắn Telegram được hỗ trợ.")
        else:
            await direct_link(message, context, raw)
    elif raw.startswith("http://"):
        await message.reply_text("❌ Chỉ nhận link HTTPS.")
    else:
        await find_music(message, context, raw)


async def command_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await allowed(update):
        await parse_request(update.message, context, " ".join(context.args))


async def plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await allowed(update):
        await parse_request(update.message, context, update.message.text)


async def forwarded_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update):
        return
    media = update.message.audio or update.message.document
    if media is None or not (update.message.audio or (media.mime_type or "").startswith("audio/")):
        await update.message.reply_text("Chỉ nhận file âm thanh.")
        return
    if not media.file_size or media.file_size > MAX_BOT_DOWNLOAD:
        await update.message.reply_text("File gửi trực tiếp vào bot cần ≤20 MB. Với file lớn hơn, thử link tin nhắn Telegram (tối đa 48 MB).")
        return

    async def op(directory):
        ext = Path(media.file_name or "").suffix.lower()
        if ext not in ALLOWED_SUFFIXES:
            ext = ".mp3" if media.mime_type == "audio/mpeg" else ".m4a"
        dest = directory / f"forwarded{ext}"
        f = await context.bot.get_file(media.file_id)
        await f.download_to_drive(custom_path=dest)
        await send_audio_file(update.message, context, dest, directory,
                              title=Path(media.file_name or "Nhạc chuyển tiếp").stem)
    await deliver(update.message, context, op)


async def on_init(app: Application):
    api_id = os.getenv("TELEGRAM_API_ID", "")
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    if api_id.isdecimal() and api_hash:
        SESSION_PATH.parent.mkdir(exist_ok=True)
        client = TelegramClient(str(SESSION_PATH), int(api_id), api_hash)
        await client.connect()
        if await client.is_user_authorized():
            app.bot_data["user_client"] = client
            LOG.info("Personal Telegram session connected")
        else:
            await client.disconnect()
            LOG.warning("No user session; run python login.py")


async def on_shutdown(app: Application):
    client = app.bot_data.get("user_client")
    if client:
        await client.disconnect()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    owner = os.getenv("ALLOWED_USER_ID", "")
    if not token:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN trong .env")
    if not owner.isdecimal():
        raise SystemExit("Thiếu ALLOWED_USER_ID (chạy bot với tạm ID của bạn hoặc lấy từ @userinfobot).")
    app = ApplicationBuilder().token(token).post_init(on_init).post_shutdown(on_shutdown).build()
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler(["tim", "nhac", "link"], command_music))
    app.add_handler(CallbackQueryHandler(chosen, pattern=r"^track:\d+$"))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.ALL, forwarded_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text))
    LOG.info("Personal music bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()