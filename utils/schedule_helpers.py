"""
utils/schedule_helpers.py
Các hàm tính toán thời gian lịch trình — thuần (pure function), không I/O,
không side-effect. Dùng để hiển thị "lần chạy tiếp theo" trên scheduler_page.py
mà KHÔNG cần import trực tiếp scheduler_runner.py (tránh nạp lại logging
handler của một process khác vào process Streamlit).
"""
from datetime import datetime, timedelta


def calc_reminder_time(reply_h: int, reply_m: int, minutes_before: int = 30) -> tuple:
    """
    Tính giờ:phút nhắc nhở trước deadline.
    Dùng timedelta để tránh edge case giờ âm khi reply_h = 0 và reply_m < minutes_before
    (ví dụ deadline 00:15 → nhắc nhở 23:45 ngày trước, không phải giờ "-1").
    """
    deadline_dt = datetime(2000, 1, 1, reply_h, reply_m)
    reminder_dt = deadline_dt - timedelta(minutes=minutes_before)
    return reminder_dt.hour, reminder_dt.minute


def calc_next_daily_run(hour: int, minute: int, now: datetime = None) -> datetime:
    """
    Tính thời điểm chạy tiếp theo của một job hàng ngày (kiểu cron hour:minute).
    Trả về hôm nay nếu giờ đó chưa qua, ngược lại trả về ngày mai.
    """
    now       = now or datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def format_next_run(dt: datetime) -> str:
    """Format thời điểm thành chuỗi dễ đọc: 'Hôm nay HH:MM' / 'Ngày mai HH:MM'."""
    now = datetime.now()
    if dt.date() == now.date():
        return f"Hôm nay {dt.strftime('%H:%M')}"
    if dt.date() == (now.date() + timedelta(days=1)):
        return f"Ngày mai {dt.strftime('%H:%M')}"
    return dt.strftime("%d/%m %H:%M")