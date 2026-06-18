"""
utils/constants.py
Tất cả hằng số, đường dẫn và giá trị mặc định dùng chung toàn dự án.
Thay thế các magic strings và path constants bị lặp lại ở nhiều file.
"""
from pathlib import Path

# ── Thư mục gốc ───────────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).parent.parent
CONFIG_DIR = ROOT_DIR / "config"

# ── File paths (định nghĩa MỘT lần duy nhất) ─────────────────────────────────
STATE_FILE   = CONFIG_DIR / "state.json"
LOG_FILE     = CONFIG_DIR / "logs.json"
CONFIG_FILE  = CONFIG_DIR / "settings.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

# ── Giới hạn lưu trữ ─────────────────────────────────────────────────────────
MAX_LOG_ENTRIES     = 200
MAX_HISTORY_ENTRIES = 500
MAX_BACKUPS         = 7

# ── Email defaults ────────────────────────────────────────────────────────────
DEFAULT_IMAP_SERVER = "imap.gmail.com"
DEFAULT_SMTP_SERVER = "smtp.gmail.com"
DEFAULT_SOC_SENDER  = "SOC Canh bao"
DEFAULT_BRANCH      = "HUE"
DEFAULT_PASSWORD    = "soc2026"  # Chỉ dùng khi chưa set password_hash

# ── Scheduler defaults ────────────────────────────────────────────────────────
DEFAULT_SCAN_INTERVAL = 30   # phút
DEFAULT_REPLY_HOUR    = 11
DEFAULT_REPLY_MINUTE  = 45
SCHEDULER_TIMEZONE    = "Asia/Ho_Chi_Minh"  # 1 nơi duy nhất, trước đây lặp lại 4 lần
                                             # trong scheduler_runner.py (DRY violation)

# ── Cảnh báo khi quét email thất bại liên tiếp ───────────────────────────────
# Nếu IMAP login thất bại (App Password hết hạn/bị đổi...) liên tiếp quá số
# lần này, hệ thống gửi 1 email cảnh báo cho Admin (không spam lặp lại).
MAX_CONSECUTIVE_SCAN_FAILURES = 5

# ── Phiên đăng nhập ───────────────────────────────────────────────────────────
SESSION_TIMEOUT_HOURS = 8

# ── Google Sheets ─────────────────────────────────────────────────────────────
DEFAULT_SPREADSHEET_ID = "11A4TuYjE3iLU92IvYK3UlOclB2baOd7Yawd4LyGrsW8"

# ── Cấu trúc state mặc định (1 nguồn sự thật duy nhất) ──────────────────────
DEFAULT_STATE: dict = {
    "last_scan":             None,
    "last_scan_date":        None,   # "dd/mm/yyyy" — chỉ mang tính thông tin (ngày job quét chạy)
    "last_email_sent":       None,
    "last_sent_report_date": None,   # report_date ĐÃ gửi thành công gần nhất
                                      # → dùng để chặn gửi lại nội dung cũ khi SOC
                                      #   không gửi email mới (so sánh với report_date hiện tại)
    "red_indicators":        [],
    "report_date":           None,
    "deadline":              None,
    "status":                "idle",
    "total_scans":           0,
    "total_emails_sent":     0,
    "latest_email_sender":   "",
    "latest_email_subject":  "",
    "latest_email_date":     "",
    "consecutive_scan_failures": 0,      # số lần quét IMAP thất bại liên tiếp
    "scan_failure_alert_sent":   False,  # đã gửi cảnh báo cho lần lỗi này chưa
                                          # (tránh gửi lại mỗi 30 phút khi vẫn đang lỗi)
}