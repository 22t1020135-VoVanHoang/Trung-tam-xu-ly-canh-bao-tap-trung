"""
pages/scheduler_page.py
Trang Lịch trình Tự động — cấu hình APScheduler, xem nhật ký, chạy thủ công.

Thay đổi so với bản cũ:
  - Xóa STATE_FILE / CONFIG_FILE / LOG_FILE / DEFAULT_STATE / load_state() duplicate
    → dùng utils.constants + utils.state_manager
  - FIX QUAN TRỌNG: danh sách job hiển thị KHÔNG khớp với job thật trong
    scheduler_runner.py. Bản cũ hiển thị "PROGRESS_CHECK" (job này KHÔNG tồn tại
    trong code) và thiếu hẳn "SEND_REMINDER" (job này CÓ tồn tại, chạy 30 phút
    trước deadline). Đã sửa để khớp 100% với 3 job thật: scan_email, send_reminder,
    send_report.
  - Fix: job SCAN_EMAIL dùng màu "blue" nhưng CSS .dot.blue không tồn tại trong
    app.py → đổi sang "green" (đã có CSS, đồng thời hợp lý hơn vì là job định kỳ
    an toàn, không phải job cảnh báo)
  - Thêm: tính "TIẾP THEO" thực tế (trước đây luôn hiển thị "—")
  - Thêm: append_log khi lưu cấu hình lịch (trước đây hành động này không được ghi log)
  - Lưu cấu hình bằng write_json_atomic thay vì json.dump trực tiếp (tránh corrupt
    file nếu mất điện/crash giữa lúc ghi)
"""
import json
import streamlit as st
from datetime import datetime, timedelta

from utils.constants        import (
    LOG_FILE,
    DEFAULT_SCAN_INTERVAL, DEFAULT_REPLY_HOUR, DEFAULT_REPLY_MINUTE,
    SCHEDULER_TIMEZONE,
)
from utils.state_manager     import load_state, append_log, save_config
from utils.schedule_helpers import calc_reminder_time, calc_next_daily_run, format_next_run


def render(config: dict) -> None:
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>⏱️ Lịch trình Tự động</h1>
            <div class="subtitle">Cài đặt APScheduler – quét email và gửi phản hồi tự động đúng deadline</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    sched_cfg = config.get("scheduler", {})

    col1, col2 = st.columns([3, 2])
    with col1:
        _render_job_list(sched_cfg)
        st.markdown("<br>", unsafe_allow_html=True)
        _render_schedule_logs()
    with col2:
        _render_schedule_config(config, sched_cfg)
        st.markdown("<br>", unsafe_allow_html=True)
        _render_system_clock_check()
        st.markdown("<br>", unsafe_allow_html=True)
        _render_manual_actions()
        st.markdown("<br>", unsafe_allow_html=True)
        _render_startup_guide()


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — UI components
# ─────────────────────────────────────────────────────────────────────────────

def _render_job_list(sched_cfg: dict) -> None:
    """Danh sách job — khớp chính xác với 3 job thật chạy trong scheduler_runner.py."""
    st.markdown('<div class="section-label">LỊCH TRÌNH HIỆN TẠI</div>', unsafe_allow_html=True)

    scan_interval = sched_cfg.get("scan_interval_minutes", DEFAULT_SCAN_INTERVAL)
    deadline_h    = sched_cfg.get("reply_deadline_hour",   DEFAULT_REPLY_HOUR)
    deadline_m    = sched_cfg.get("reply_deadline_minute", DEFAULT_REPLY_MINUTE)
    reminder_h, reminder_m = calc_reminder_time(deadline_h, deadline_m, minutes_before=30)

    state          = load_state()
    next_scan      = _estimate_next_scan(state.get("last_scan"), scan_interval)
    scan_failures  = state.get("consecutive_scan_failures", 0)

    jobs = [
        {
            "name": "SCAN_EMAIL",
            "desc": "Quét email từ SOC Canh Bao",
            "schedule": f"Mỗi {scan_interval} phút",
            "next": next_scan,
            "color": "red" if scan_failures > 0 else "green",
            "warning": (
                f"⚠ Đang lỗi {scan_failures} lần liên tiếp — kiểm tra App Password/IMAP"
                if scan_failures > 0 else None
            ),
        },
        {
            "name": "SEND_REMINDER",
            "desc": "Nhắc nhở Admin trước deadline 30 phút",
            "schedule": f"Hàng ngày lúc {reminder_h:02d}:{reminder_m:02d}",
            "next": format_next_run(calc_next_daily_run(reminder_h, reminder_m)),
            "color": "orange",
            "warning": None,
        },
        {
            "name": "AUTO_REPLY",
            "desc": "Tổng hợp Sheets & gửi email phản hồi",
            "schedule": f"Hàng ngày lúc {deadline_h:02d}:{deadline_m:02d}",
            "next": format_next_run(calc_next_daily_run(deadline_h, deadline_m)),
            "color": "red",
            "warning": None,
        },
    ]

    for job in jobs:
        status_text  = "⚠ lỗi liên tiếp" if job["warning"] else "● active"
        status_color = "#E53E3E" if job["warning"] else "#48BB78"
        warning_html = (
            f'<div style="margin-top:8px; padding:8px 12px; background:rgba(229,62,62,0.1); '
            f'border-radius:3px; font-size:11px; color:#FEB2B2;">{job["warning"]}</div>'
            if job["warning"] else ""
        )
        st.markdown(f"""
        <div class="config-section" style="padding:16px 20px; margin-bottom:10px;">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                <div class="dot {job['color']}"></div>
                <span style="font-family:var(--mono); font-size:12px; font-weight:600; color:var(--text);">{job['name']}</span>
                <span style="margin-left:auto; font-family:var(--mono); font-size:10px; color:{status_color}; text-transform:uppercase;">{status_text}</span>
            </div>
            <div style="font-size:13px; color:var(--text-muted); margin-bottom:6px;">{job['desc']}</div>
            <div style="display:flex; gap:24px; font-size:11px; font-family:var(--mono);">
                <span><span style="color:var(--text-muted);">LỊCH:</span> <span style="color:var(--text);">{job['schedule']}</span></span>
                <span><span style="color:var(--text-muted);">TIẾP THEO:</span> <span style="color:var(--text);">{job['next']}</span></span>
            </div>
            {warning_html}
        </div>
        """, unsafe_allow_html=True)


def _render_schedule_logs() -> None:
    """5 log gần nhất liên quan đến scheduler (quét / nhắc nhở / gửi báo cáo)."""
    st.markdown('<div class="section-label">NHẬT KÝ LỊCH TRÌNH</div>', unsafe_allow_html=True)

    logs = _load_recent_logs()
    sched_logs = [
        l for l in logs
        if l.get("action", "").startswith(("SCAN", "AUTO", "REMINDER"))
    ][:5]

    if not sched_logs:
        st.markdown('<div class="alert-box info">Chưa có log lịch trình.</div>', unsafe_allow_html=True)
        return

    for entry in sched_logs:
        color = "green" if entry.get("status") == "success" else "red"
        st.markdown(f"""
        <div class="timeline-item">
            <div class="timeline-time">{entry.get('time','')}</div>
            <div class="timeline-content">
                <div class="timeline-title">{entry.get('action','')}</div>
                <div class="timeline-desc">{entry.get('detail','')}</div>
            </div>
            <div class="dot {color}" style="margin-top:6px;"></div>
        </div>
        """, unsafe_allow_html=True)


def _render_schedule_config(config: dict, sched_cfg: dict) -> None:
    st.markdown('<div class="section-label">CẤU HÌNH LỊCH TRÌNH</div>', unsafe_allow_html=True)

    scan_interval = sched_cfg.get("scan_interval_minutes", DEFAULT_SCAN_INTERVAL)
    deadline_h    = sched_cfg.get("reply_deadline_hour",   DEFAULT_REPLY_HOUR)
    deadline_m    = sched_cfg.get("reply_deadline_minute", DEFAULT_REPLY_MINUTE)

    new_interval   = st.number_input("Quét email mỗi (phút)", min_value=5, max_value=120, value=scan_interval)
    st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
    new_deadline_h = st.number_input("Giờ gửi tự động (h)", min_value=0, max_value=23, value=deadline_h)
    new_deadline_m = st.number_input("Phút gửi tự động (m)", min_value=0, max_value=59, value=deadline_m)

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("💾 Lưu cấu hình lịch", type="primary", use_container_width=True):
        config.setdefault("scheduler", {})
        config["scheduler"]["scan_interval_minutes"] = new_interval
        config["scheduler"]["reply_deadline_hour"]   = new_deadline_h
        config["scheduler"]["reply_deadline_minute"] = new_deadline_m

        save_config(config)  # Atomic + lock, dùng chung với mọi trang khác

        append_log(
            "SCHEDULE_CONFIG",
            f"Cập nhật lịch: quét mỗi {new_interval}p, gửi lúc {new_deadline_h:02d}:{new_deadline_m:02d}",
            "success",
        )
        st.markdown('<div class="alert-box success">✅ Đã lưu cấu hình lịch trình.</div>', unsafe_allow_html=True)
        st.rerun()


def _render_system_clock_check() -> None:
    """
    Hiển thị giờ hệ thống hiện tại để Admin tự đối chiếu với giờ Việt Nam thật.
    Toàn bộ datetime.now()/date.today() trong hệ thống dùng giờ HỆ ĐIỀU HÀNH,
    không tự quy đổi theo SCHEDULER_TIMEZONE — nếu máy chủ đặt sai múi giờ,
    mọi job (quét, nhắc nhở, gửi báo cáo) có thể lệch giờ chạy thực tế.
    Đây chỉ là hiển thị tham khảo, không tự động phát hiện lệch (để tránh phụ
    thuộc thêm thư viện múi giờ chưa chắc tương thích trên Windows).
    """
    st.markdown('<div class="section-label">KIỂM TRA GIỜ HỆ THỐNG</div>', unsafe_allow_html=True)
    now_str = datetime.now().strftime("%H:%M:%S — %d/%m/%Y")
    st.markdown(f"""
    <div class="alert-box info" style="font-size:12px;">
        🕐 Giờ máy chủ hiện tại: <strong style="font-family:var(--mono);">{now_str}</strong><br>
        Múi giờ lịch trình đang cấu hình: <code style="font-size:11px;">{SCHEDULER_TIMEZONE}</code><br>
        <span style="color:var(--text-muted);">
            Đối chiếu với giờ thực tế Việt Nam — nếu lệch, kiểm tra lại múi giờ
            của máy chủ Windows (Settings → Time & Language).
        </span>
    </div>
    """, unsafe_allow_html=True)


def _render_manual_actions() -> None:
    st.markdown('<div class="section-label">CHẠY THỦ CÔNG</div>', unsafe_allow_html=True)

    if st.button("🔍 Quét Email Ngay", use_container_width=True):
        st.session_state.page = "email_scan"
        st.session_state.trigger_scan = True
        st.rerun()

    if st.button("📤 Gửi Báo cáo Ngay", use_container_width=True):
        st.session_state.page = "send_email"
        st.rerun()


def _render_startup_guide() -> None:
    with st.expander("📖 Hướng dẫn khởi động hệ thống"):
        st.markdown("""
        <div style="font-size:13px; line-height:2.2; color:#E8E8EC;">
            1. Mở <strong>File Explorer</strong> (phím <code style="background:#2A2A30; padding:2px 6px; border-radius:3px;">Windows + E</code>)<br>
            2. Vào thư mục <code style="background:#2A2A30; padding:2px 6px; border-radius:3px;">E:\\soc-hue\\</code><br>
            3. Bấm đúp chuột vào file <code style="background:#E53E3E; color:white; padding:2px 8px; border-radius:3px;">start_soc.bat</code><br>
            <span style="color:#48BB78;">→ Hệ thống tự động mở 2 cửa sổ: <strong>App</strong> và <strong>Watchdog</strong>.</span>
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_recent_logs() -> list:
    """Đọc logs.json an toàn, trả về [] nếu file lỗi hoặc chưa tồn tại."""
    if not LOG_FILE.exists():
        return []
    try:
        content = LOG_FILE.read_text(encoding="utf-8").strip()
        return json.loads(content) if content else []
    except Exception:
        return []


def _estimate_next_scan(last_scan_str: str, interval_minutes: int) -> str:
    """
    Ước tính lần quét tiếp theo = lần quét cuối + interval.
    Trả về '—' nếu chưa từng quét (không có cơ sở để ước tính).
    """
    if not last_scan_str:
        return "—"
    try:
        last_dt = datetime.strptime(last_scan_str, "%d/%m/%Y %H:%M")
        next_dt = last_dt + timedelta(minutes=interval_minutes)
        return format_next_run(next_dt)
    except Exception:
        return "—"