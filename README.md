# BOTTELE1 — Telegram bot tải nhạc cá nhân

Bot Python chạy trên Windows, **chỉ trả lời chủ sở hữu** trong cuộc trò chuyện riêng. Bot nhận tên bài hát, link MP3/M4A công khai, link tin nhắn Telegram có chứa nhạc và file nhạc được chuyển tiếp vào bot. Không cần cấp quyền admin cho bot trong nhóm.

## Những gì bot làm được

- `/tim ten bai hat` hoặc gửi tên bài hát: tìm trên **Jamendo**, chỉ hiển thị các bài mà API trả `audiodownload_allowed=true` và có URL giấy phép Creative Commons. Bấm nút để nhận MP3.
- `/link https://example.org/song.mp3`: tải file MP3/M4A qua đường dẫn **HTTPS trực tiếp**, tối đa 48 MiB.
- `/link https://t.me/tenkenh/1234`: tìm file âm thanh trong một tin nhắn của kênh/nhóm công khai.
- `/link https://t.me/c/123456789/987`: tìm file âm thanh trong một tin nhắn của **nhóm/kênh riêng tư mà tài khoản Telegram đã đăng nhập có quyền xem**. Link topic dạng `t.me/c/123456789/100/987` cũng được hỗ trợ.
- Chuyển tiếp file nhạc vào bot hoặc gửi file trực tiếp (giới hạn tải xuống từ Bot API khoảng 20 MB).
- File M4A/OGG/FLAC/WAV được chuyển sang MP3 bằng FFmpeg nếu cài FFmpeg. File MP3 gốc được gửi không mã hóa lại.
- Chỉ `ALLOWED_USER_ID` có thể dùng tính năng; tin nhắn nhóm bị bỏ qua. File tải xuống được tạo tạm rồi xóa.

**Giới hạn:** Không tự động đọc toàn bộ tin nhắn, không vượt quyền truy cập nhóm/kênh, không lấy nhạc từ link tin nhắn riêng tư 1:1 nếu Telegram không cung cấp message link, không truy cập Secret Chats, không tải nội dung bị bật bảo vệ. Link từ YouTube/Spotify/trang nghe nhạc **không** phải link file MP3 trực tiếp. Chỉ sử dụng nhạc mà bạn có quyền tải/lưu và tuân thủ giấy phép sử dụng.

## 1. Cài đặt trên Windows

Cần Python **3.11+**, Git và Telegram cài trên điện thoại. Mở PowerShell:

```powershell
git clone https://github.com/LeQuangAnhCT/BOTTELE1.git
cd BOTTELE1
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Không cần kích hoạt virtual environment. Nếu muốn chuyển M4A/OGG/FLAC/WAV sang MP3, cài FFmpeg trên Windows và mở lại PowerShell:

```powershell
winget install --id Gyan.FFmpeg -e
ffmpeg -version
```

## 2. Điền `.env` (KHÔNG đưa lên GitHub)

- **`TELEGRAM_BOT_TOKEN`**: vào [@BotFather](https://t.me/BotFather), `/newbot`, lấy token.
- **`ALLOWED_USER_ID`**: số ID Telegram của bạn; hỏi [@userinfobot](https://t.me/userinfobot) hoặc bot của bạn qua `/id` (sau khi bot đang chạy). *Điền đúng ID trước khi khởi động bot.*
- **`JAMENDO_CLIENT_ID`**: tạo ứng dụng tại https://devportal.jamendo.com/ để nhận API Client ID.
- **`TELEGRAM_API_ID`** và **`TELEGRAM_API_HASH`**: đăng nhập https://my.telegram.org/apps, tạo ứng dụng cá nhân và lấy 2 giá trị này; dùng để kết nối **tài khoản Telegram của chính bạn** qua Telethon (không liên quan BotFather).

Mẫu:

```dotenv
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
ALLOWED_USER_ID=123456789
JAMENDO_CLIENT_ID=YOUR_JAMENDO_CLIENT_ID
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=YOUR_API_HASH
```

Bạn tự nhập tất cả khóa trên máy cá nhân; **không gửi Bot Token, OTP, 2FA, API Hash hay file `.session` cho ai**, kể cả người hỗ trợ.

## 3. Đăng nhập Telegram cá nhân để đọc link tin nhắn

```powershell
.\.venv\Scripts\python.exe login.py
```

Chỉ lần đăng nhập đầu tiên, Telethon có thể hỏi **số điện thoại, mã đăng nhập Telegram và mật khẩu 2 bước** trong terminal local. Phiên đăng nhập được lưu trong `sessions/my_telegram.session` trên máy bạn, không nằm trên GitHub.

**Cảnh báo:** File `.session` có quyền truy cập tài khoản Telegram tương ứng. Bảo vệ máy tính và không gửi/upload file session; nếu lộ, vào **Telegram → Settings → Devices** để thu hồi phiên đó. Muốn ngừng cấp quyền, đóng bot, thu hồi phiên trong Telegram và xóa `sessions/`.

Bot chỉ tải được từ nhóm/kênh bạn đã có quyền xem. Link riêng tư `t.me/c/...` yêu cầu đã tham gia nhóm/kênh; link 1:1 không có định dạng message link phù hợp, hãy chuyển tiếp file âm thanh vào bot.

## 4. Chạy bot

```powershell
.\.venv\Scripts\python.exe bot.py
```

Mở cuộc trò chuyện riêng với bot trên Telegram → `Start`:

```text
/tim acoustic chill
/link https://example.org/track.mp3
/link https://t.me/tenkenh/123
/link https://t.me/c/123456789/987
/id
```

Hoặc gửi thẳng tên bài, link, file nhạc. Dừng bot bằng `Ctrl+C`. Bot dùng **long polling**, vì vậy khi tắt máy/dừng terminal thì bot cũng dừng. Không cần deploy Vercel/Supabase để chạy trên PC.

## 5. Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q bot.py links.py login.py
```

Kiểm thử đơn vị không cần đăng nhập Telegram. Chức năng thực tế cần kiểm tra thêm bằng tài khoản và Bot Token của chính bạn.

## Vấn đề thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| `Thiếu TELEGRAM_BOT_TOKEN` | Điền token trong `.env` ở thư mục gốc. |
| Bot báo không có quyền | Kiểm tra `ALLOWED_USER_ID` là **ID số của tài khoản bạn**, không phải ID bot. |
| Bot không đọc được `t.me/c/...` | Chạy `login.py` trên cùng máy/thư mục; tài khoản phải tham gia nhóm/kênh. Sau khi login, **khởi động lại bot**. |
| `JAMENDO_CLIENT_ID` | Tạo Client ID trên Jamendo, không phải API của Telegram. |
| Không tìm thấy bài | Jamendo không chứa mọi bài hát thương mại và một số bài không cho phép tải. |
| `File vượt giới hạn` | Bot API gửi tối đa khoảng 50 MB; dự án áp mức an toàn 48 MiB. |
| `Cài FFmpeg` | Chạy `winget install --id Gyan.FFmpeg -e`, mở lại terminal và kiểm tra `ffmpeg -version`. |
| Bot không phản hồi khi tắt Windows | Đây là bot chạy local; cần máy và tiến trình đang chạy hoặc triển khai server riêng an toàn. |

## Nguồn chính thức

- [Telegram Bot API](https://core.telegram.org/bots/api#sendaudio)
- [Telegram message links](https://core.telegram.org/api/links)
- [Telethon sessions/entities](https://docs.telethon.dev/en/stable/concepts/entities.html)
- [Jamendo tracks API](https://developer.jamendo.com/v3.0/tracks)

**Bảo mật:** `.gitignore` đã chặn `.env`, phiên đăng nhập, nhạc và thư mục venv; không được xóa những quy tắc này khi commit.