"""
pages/logs_page.py
Trang Nhật ký Hoạt động — xem, lọc, xuất CSV nhật ký toàn hệ thống.

Thay đổi so với bản cũ:
  - Xóa LOG_FILE hardcode → dùng utils.constants.LOG_FILE
  - Đọc logs.json an toàn (try/except + utf-8) — bản cũ dùng open() trần,
    nếu file lỗi/corrupt sẽ crash toàn bộ trang
  - Danh sách filter hành động giờ tự động lấy từ dữ liệu thật, không còn
    hardcode cứng ["EMAIL_SENT", "SCAN_EMAIL", "ERROR"] — danh sách cũ đã lạc
    hậu, thiếu AUTO_REPLY, REMINDER, SCHEDULE_CONFIG, CONFIG_UPDATE...
  - Nút xoá nhật ký & nút thêm log demo dùng write_json_atomic/append_log
    thay vì json.dump trực tiếp (đồng bộ với toàn hệ thống)
"""
import streamlit as st
import json
from datetime import datetime

from utils.constants     import LOG_FILE
from utils.state_manager import append_log, write_json_atomic


def render() -> None:
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>📜 Nhật ký Hoạt động</h1>
            <div class="subtitle">Lịch sử quét email, tổng hợp và gửi báo cáo</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    logs = _load_logs()

    col1, col2 = st.columns([3, 1])
    with col2:
        action_filter, status_filter = _render_filters(logs)
        _render_stats(logs)
    with col1:
        _render_log_list(logs, action_filter, status_filter)


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — UI components
# ─────────────────────────────────────────────────────────────────────────────

def _render_filters(logs: list) -> tuple:
    st.markdown('<div class="section-label">LỌC NHẬT KÝ</div>', unsafe_allow_html=True)

    # Danh sách hành động lấy TỪ DỮ LIỆU THẬT, không hardcode cứng nữa
    action_types = sorted({l.get("action", "") for l in logs if l.get("action")})
    action_filter = st.selectbox("Loại hành động", ["Tất cả"] + action_types)
    status_filter = st.selectbox("Trạng thái", ["Tất cả", "success", "error", "warning"])

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ Xoá nhật ký", use_container_width=True):
        write_json_atomic(LOG_FILE, [])
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    return action_filter, status_filter


def _render_stats(logs: list) -> None:
    total         = len(logs)
    success_count = len([l for l in logs if l.get("status") == "success"])
    error_count   = len([l for l in logs if l.get("status") == "error"])

    st.markdown(f"""
    <div class="metric-card blue" style="padding:14px; margin-bottom:8px;">
        <div class="label">Tổng log</div>
        <div class="value">{total}</div>
    </div>
    <div class="metric-card green" style="padding:14px; margin-bottom:8px;">
        <div class="label">Thành công</div>
        <div class="value">{success_count}</div>
    </div>
    <div class="metric-card red" style="padding:14px; margin-bottom:8px;">
        <div class="label">Lỗi</div>
        <div class="value">{error_count}</div>
    </div>
    """, unsafe_allow_html=True)


def _render_log_list(logs: list, action_filter: str, status_filter: str) -> None:
    st.markdown('<div class="section-label">NHẬT KÝ GẦN ĐÂY</div>', unsafe_allow_html=True)

    filtered = logs
    if action_filter != "Tất cả":
        filtered = [l for l in filtered if l.get("action") == action_filter]
    if status_filter != "Tất cả":
        filtered = [l for l in filtered if l.get("status") == status_filter]

    if not filtered:
        st.markdown('<div class="alert-box info">Không có nhật ký nào phù hợp với bộ lọc.</div>', unsafe_allow_html=True)
        if not logs and st.button("➕ Thêm log demo"):
            _add_demo_logs()
            st.rerun()
        return

    for entry in filtered:
        status = entry.get("status", "info")
        color  = "green" if status == "success" else ("red" if status == "error" else "orange")
        icon   = "✅" if status == "success" else ("❌" if status == "error" else "⚠️")

        st.markdown(f"""
        <div class="timeline-item">
            <div class="timeline-time">{entry.get('time','')}</div>
            <div class="timeline-content">
                <div class="timeline-title">{icon} {entry.get('action','')}</div>
                <div class="timeline-desc">{entry.get('detail','')}</div>
            </div>
            <div class="dot {color}" style="margin-top:6px; flex-shrink:0;"></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    import pandas as pd
    df  = pd.DataFrame(filtered)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Xuất CSV",
        data=csv,
        file_name=f"soc_logs_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — Data
# ─────────────────────────────────────────────────────────────────────────────

def _load_logs() -> list:
    """Đọc logs.json an toàn — trả về [] nếu file chưa tồn tại hoặc bị lỗi."""
    if not LOG_FILE.exists():
        return []
    try:
        content = LOG_FILE.read_text(encoding="utf-8").strip()
        return json.loads(content) if content else []
    except Exception:
        return []


def _add_demo_logs() -> None:
    """Thêm 2 log mẫu để minh hoạ giao diện khi hệ thống chưa có log nào."""
    append_log("EMAIL_SENT", "Gửi đến soccanh@fpt.com – 3 chỉ số đỏ", "success")
    append_log("SCAN_EMAIL", "Quét email từ SOC Canh bao – Tìm thấy 2 email", "success")