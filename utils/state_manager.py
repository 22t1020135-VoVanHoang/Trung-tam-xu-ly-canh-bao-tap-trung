"""
utils/state_manager.py
Quản lý state / log / history / config tập trung — 1 nguồn duy nhất cho mọi
việc đọc/ghi file JSON trong dự án.

Giải quyết:
  - DRY #1: load_state / save_state bị copy ở 5 file → 1 nơi duy nhất
  - DRY #2: _has_streamlit_secrets() bị copy ở 3 file
  - DRY #3: _append_log() bị copy ở 2 file
  - DRY #4: Path constants bị copy ở 7 file
  - DRY #5: load_config/save_config bị định nghĩa riêng trong app.py, ghi file
            KHÔNG atomic, KHÔNG lock (duy nhất 1 file chưa được bảo vệ)
  - Bug #1: _backup_state() NameError trong email_scan & send_email
  - Logic #3: Race condition khi ghi file đồng thời
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from utils.constants import (
    STATE_FILE, LOG_FILE, HISTORY_FILE, CONFIG_FILE,
    MAX_LOG_ENTRIES, MAX_HISTORY_ENTRIES, MAX_BACKUPS,
    DEFAULT_STATE,
    DEFAULT_IMAP_SERVER, DEFAULT_SMTP_SERVER, DEFAULT_SPREADSHEET_ID,
    DEFAULT_SCAN_INTERVAL, DEFAULT_REPLY_HOUR, DEFAULT_REPLY_MINUTE,
    DEFAULT_SOC_SENDER, DEFAULT_BRANCH,
)

log = logging.getLogger(__name__)

# ── File locking — tránh race condition khi scheduler & UI ghi đồng thời ─────
try:
    from filelock import FileLock
    _state_lock   = FileLock(str(STATE_FILE)   + ".lock")
    _log_lock     = FileLock(str(LOG_FILE)      + ".lock")
    _history_lock = FileLock(str(HISTORY_FILE)  + ".lock")
    _config_lock  = FileLock(str(CONFIG_FILE)   + ".lock")
    _FILELOCK_OK  = True
except ImportError:
    _FILELOCK_OK = False
    log.warning(
        "Thư viện 'filelock' chưa cài — race condition có thể xảy ra. "
        "Chạy: pip install filelock"
    )


# ═════════════════════════════════════════════════════════════════════════════
# STATE
# ═════════════════════════════════════════════════════════════════════════════

def load_state() -> dict:
    """
    Đọc state.json và merge với DEFAULT_STATE để đảm bảo luôn đủ keys.
    Trả về DEFAULT_STATE nếu file không tồn tại hoặc bị lỗi.
    """
    if not STATE_FILE.exists():
        return DEFAULT_STATE.copy()
    try:
        content = STATE_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return DEFAULT_STATE.copy()
        data = json.loads(content)
        # Merge: giữ data có sẵn, bổ sung keys còn thiếu từ DEFAULT_STATE
        return {**DEFAULT_STATE, **data}
    except Exception as e:
        log.warning(f"Lỗi đọc state.json: {e} — dùng default")
        _safe_delete(STATE_FILE)
        return DEFAULT_STATE.copy()


def save_state(state: dict) -> None:
    """
    Ghi state.json an toàn (atomic write) + tạo backup.
    Thread-safe nhờ filelock.
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _FILELOCK_OK:
        with _state_lock:
            write_json_atomic(STATE_FILE, state)
    else:
        write_json_atomic(STATE_FILE, state)
    _backup_state()


def _backup_state() -> None:
    """
    Tạo backup state.json, giữ tối đa MAX_BACKUPS bản gần nhất.
    Chỉ chạy nội bộ, không gọi trực tiếp từ bên ngoài.
    """
    if not STATE_FILE.exists():
        return
    try:
        backup_dir  = STATE_FILE.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"state_{timestamp}.json"
        backup_file.write_bytes(STATE_FILE.read_bytes())
        # Xóa bản cũ nếu vượt giới hạn
        backups = sorted(backup_dir.glob("state_*.json"))
        for old_file in backups[:-MAX_BACKUPS]:
            old_file.unlink(missing_ok=True)
    except Exception as e:
        log.warning(f"Backup state thất bại: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# CONFIG (settings.json)
# ═════════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    """
    Đọc settings.json. Trả về cấu trúc mặc định (dựng từ constants — KHÔNG
    hardcode lại trong app.py như bản cũ) nếu file chưa tồn tại hoặc lỗi.
    """
    if CONFIG_FILE.exists():
        try:
            content = CONFIG_FILE.read_text(encoding="utf-8").strip()
            if content:
                return json.loads(content)
        except Exception as e:
            log.warning(f"Lỗi đọc settings.json: {e} — dùng cấu hình mặc định")

    return {
        "email": {
            "address":     "",
            "password":    "",
            "imap_server": DEFAULT_IMAP_SERVER,
            "smtp_server": DEFAULT_SMTP_SERVER,
        },
        "google_sheets": {
            "spreadsheet_id":   DEFAULT_SPREADSHEET_ID,
            "credentials_path": "",
        },
        "scheduler": {
            "scan_interval_minutes": DEFAULT_SCAN_INTERVAL,
            "reply_deadline_hour":   DEFAULT_REPLY_HOUR,
            "reply_deadline_minute": DEFAULT_REPLY_MINUTE,
        },
        "soc_sender_name": DEFAULT_SOC_SENDER,
        "branch":          DEFAULT_BRANCH,
        "auth": {},
    }


def save_config(config: dict) -> None:
    """
    Ghi settings.json an toàn (atomic write + file lock).
    Fix DRY #5: bản cũ trong app.py ghi trực tiếp bằng json.dump, không lock,
    không atomic — là file JSON DUY NHẤT trong hệ thống chưa được bảo vệ.
    """
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _FILELOCK_OK:
        with _config_lock:
            write_json_atomic(CONFIG_FILE, config)
    else:
        write_json_atomic(CONFIG_FILE, config)


# ═════════════════════════════════════════════════════════════════════════════
# LOG
# ═════════════════════════════════════════════════════════════════════════════

def append_log(action: str, detail: str, status: str = "success") -> None:
    """
    Ghi một entry vào logs.json (thread-safe, giới hạn MAX_LOG_ENTRIES dòng).

    Args:
        action : Tên hành động, ví dụ "SCAN_EMAIL", "EMAIL_SENT"
        detail : Mô tả chi tiết
        status : "success" | "warning" | "error"
    """
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time":   datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "action": action,
        "detail": detail,
        "status": status,
    }
    if _FILELOCK_OK:
        with _log_lock:
            _prepend_to_json(LOG_FILE, entry, MAX_LOG_ENTRIES)
    else:
        _prepend_to_json(LOG_FILE, entry, MAX_LOG_ENTRIES)


# ═════════════════════════════════════════════════════════════════════════════
# HISTORY
# ═════════════════════════════════════════════════════════════════════════════

def append_history(
    report_date:    str,
    branch:         str,
    to_address:     str,
    subject:        str,
    red_indicators: list,
    explanations:   list,
    status:         str = "success",
) -> None:
    """
    Lưu chi tiết một lần gửi email vào history.json.
    Dùng cho cả gửi thủ công (send_email.py) lẫn gửi tự động (scheduler_runner.py).

    Args:
        report_date    : Ngày báo cáo, ví dụ "01/06/2026"
        branch         : Chi nhánh, ví dụ "HUE"
        to_address     : Địa chỉ nhận
        subject        : Tiêu đề email
        red_indicators : Danh sách chỉ số đỏ
        explanations   : Danh sách dict từ collect_all_explanations()
        status         : "success" | "error"
    """
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "id":              datetime.now().strftime("%Y%m%d_%H%M%S"),
        "sent_at":         datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "report_date":     report_date,
        "branch":          branch,
        "to_address":      to_address,
        "subject":         subject,
        "red_indicators":  red_indicators,
        "explanations": [
            {
                "indicator":  e.get("indicator", ""),
                "sheet_name": e.get("sheet_name", ""),
                "count":      e.get("count", 0),
            }
            for e in explanations
        ],
        "total_records": sum(e.get("count", 0) for e in explanations),
        "status":         status,
    }
    if _FILELOCK_OK:
        with _history_lock:
            _prepend_to_json(HISTORY_FILE, entry, MAX_HISTORY_ENTRIES)
    else:
        _prepend_to_json(HISTORY_FILE, entry, MAX_HISTORY_ENTRIES)


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS (private)
# ═════════════════════════════════════════════════════════════════════════════

def has_streamlit_secrets() -> bool:
    """
    Kiểm tra Streamlit secrets có chứa google_service_account không.
    Thay thế 3 bản copy trong send_email.py, settings_page.py, sheets_view.py.
    """
    try:
        import streamlit as st
        return hasattr(st, "secrets") and "google_service_account" in st.secrets
    except Exception:
        return False


def write_json_atomic(path: Path, data) -> None:
    """
    Ghi JSON theo kiểu atomic: ghi ra file .tmp trước, sau đó rename.
    Đảm bảo nếu crash giữa chừng, file gốc không bị hỏng.
    Public — dùng lại được ở các trang khác (ví dụ scheduler_page.py lưu settings.json).
    """
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)  # atomic trên cùng filesystem (Windows & Linux)


def _prepend_to_json(path: Path, entry: dict, max_entries: int) -> None:
    """
    Đọc danh sách JSON từ file, thêm entry vào đầu, giới hạn max_entries.
    """
    entries = []
    if path.exists():
        try:
            content = path.read_text(encoding="utf-8").strip()
            entries = json.loads(content) if content else []
        except Exception:
            entries = []
    entries.insert(0, entry)
    write_json_atomic(path, entries[:max_entries])


def _safe_delete(path: Path) -> None:
    """Xóa file mà không raise exception."""
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass