"""Explicit, local Telethon login. Keep the .session file secret."""
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon.sync import TelegramClient

load_dotenv()
api_id = os.getenv("TELEGRAM_API_ID", "")
api_hash = os.getenv("TELEGRAM_API_HASH", "")
if not api_id.isdecimal() or not api_hash:
    raise SystemExit("Cần TELEGRAM_API_ID và TELEGRAM_API_HASH trong .env (my.telegram.org).")

session = Path("sessions") / "my_telegram"
session.parent.mkdir(exist_ok=True)
print("Chỉ đăng nhập trên máy của bạn. Không gửi mã OTP hoặc file .session cho người khác.")
with TelegramClient(str(session), int(api_id), api_hash) as client:
    user = client.get_me()
    print(f"Đã đăng nhập tài khoản Telegram: {user.first_name} (ID: {user.id})")
    print("Phiên đăng nhập được lưu trong thư mục sessions/ và không push lên GitHub.")